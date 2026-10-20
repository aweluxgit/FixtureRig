#
# This module handles everything related to the execution logic and order of the tests
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Execution
# Model", "Base classes" and "Design Constraints and Open Decisions"):
#
# - Tests run strictly in configuration order (a depth first walk of the
#   config tree, i.e. the order of Config.testcases()). There is no
#   reordering or parallelism.
#
# - A testcase parameter whose type hint is a base.Fixture subclass is a
#   reference to a configured fixture *by name*: the config value must be the
#   `name` of a `fixture` entry. This is the smallest coherent answer to
#   "What syntax identifies a reference to another fixture?" and is enforced
#   only through type hints, so plain string parameters are never mistaken
#   for references.
#
# - Fixtures are instantiated lazily, on first reference, and then shared by
#   every later testcase (and fixture) that references the same name. On
#   creation a fixture gets `setup()` and `self_test()`. A fixture that fails
#   either is remembered as broken, so later tests that need it are skipped
#   immediately instead of retrying the hardware.
#
# - Per testcase, the fixtures it references are `start()`ed before the
#   testcase's `setup()` and `stop()`ped after its `teardown()`. Fixtures the
#   previous testcase used but the current one does not get `lazy_stop()`.
#   After the last testcase every created fixture gets `disconnect()` and then
#   `teardown()`, in reverse creation order.
#
# - Verdict classification:
#     * configuration / class loading / argument mapping / fixture problems
#       -> SKIPPED (the test never ran; see "skipped: ... due to a
#       configuration or fixture issue").
#     * test() returns True/False -> PASSED/FAILED.
#     * test() returns a Verdict -> used as-is if PASSED/FAILED/SKIPPED;
#       the runner-only statuses (ERROR, NONE, KNOWNFAILED) -> ERROR.
#     * test() returns None -> NONE. Scripts (where NONE is acceptable) are
#       not modeled yet, so NONE is reported as not passed.
#     * test() raises VerdictException -> its verdict, with the same rules.
#     * any other exception from setup()/test() -> ERROR.
#     * an exception from teardown() or a fixture's start()/stop() turns an
#       otherwise PASSED result into ERROR; a worse verdict is kept.
#     * a FAILED verdict the test reported through report().verdict() /
#       report().check() turns an otherwise PASSED result into FAILED, so a
#       test can record several checks and still return True at the end.
#
# - Reporting (see fixturerig.report): the run reports into one ReportStream,
#   which is activated for the whole run so report() inside tests and
#   fixtures reaches it. The runner reports RunStarted/RunFinished around the
#   run, GroupStarted/GroupFinished around every test group, and
#   TestStarted/TestFinished around every testcase - also for testcases that
#   are skipped before they run. TestStarted carries the test specification:
#   class, class docstring, configured params and traceability IDs.
#

from __future__ import annotations

import logging
import time
import inspect
from dataclasses import dataclass
from typing import Any

from fixturerig.base.fixture import Fixture
from fixturerig.base.verdict import Verdict, VerdictException, VerdictStatus
from fixturerig.config.model import Config, ConfigError
from fixturerig.config.model import Fixture as FixtureEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.config.model import TestGroup
from fixturerig.core.class_loader import ClassLoadError, load_class
from fixturerig.core.inheritance import ArgumentMappingError, map_config_to_method_args
from fixturerig.report.events import (
    GroupFinished,
    GroupStarted,
    RunFinished,
    RunStarted,
    TestFinished,
    TestStarted,
)
from fixturerig.report.stream import ReportStream

logger = logging.getLogger(__name__)

# Statuses a testcase may report itself; the rest are reserved for the runner.
_TEST_SETTABLE = {VerdictStatus.PASSED, VerdictStatus.FAILED, VerdictStatus.SKIPPED}


class FixtureError(Exception):
    """Raised when a configured fixture cannot be resolved, created or set up."""


@dataclass
class TestResult:
    """The outcome of running one configured testcase."""

    name: str
    verdict: Verdict
    duration: float = 0.0

    @property
    def passed(self) -> bool:
        return self.verdict.passed


class FixtureManager:
    """Creates, shares and tears down the fixtures configured in a Config."""

    def __init__(self, config: Config):
        self._entries: dict[str, FixtureEntry] = {}
        for entry in config.fixtures():
            if entry.name in self._entries:
                raise ConfigError(f"Fixture {entry.name!r} is configured more than once")
            self._entries[entry.name] = entry
        self._instances: dict[str, Fixture] = {}  # insertion order == creation order
        self._broken: dict[str, str] = {}
        self._creating: list[str] = []
        self._active: set[str] = set()

    def resolver(self, used: set[str]):
        """Return an `instantiate_fixture` callback for map_config_to_method_args
        that records every fixture name it resolves into `used`."""

        def instantiate_fixture(value: Any, hint: type) -> Fixture:
            name = self._check_reference(value, hint)
            instance = self.get(name)
            used.add(name)
            return instance

        return instantiate_fixture

    def get(self, name: str) -> Fixture:
        """Return the fixture instance for `name`, creating and setting it up on first use."""
        if name in self._instances:
            return self._instances[name]
        if name in self._broken:
            raise FixtureError(f"Fixture {name!r} is unavailable: {self._broken[name]}")
        if name in self._creating:
            cycle = " -> ".join([*self._creating, name])
            raise FixtureError(f"Circular fixture reference: {cycle}")

        self._creating.append(name)
        try:
            instance = self._create(self._entries[name])
        except Exception as exc:
            self._broken[name] = str(exc)
            if isinstance(exc, FixtureError):
                raise
            raise FixtureError(f"Fixture {name!r} could not be created: {exc}") from exc
        finally:
            self._creating.pop()

        self._instances[name] = instance
        return instance

    def activate(self, names: set[str]) -> None:
        """Lazy-stop fixtures no longer needed, then start the ones `names` requires.

        If a start() fails, the fixtures already started are stopped again
        and the exception is re-raised.
        """
        for name in self._ordered(self._active - names):
            self._call(name, "lazy_stop")
        self._active = set()
        for name in self._ordered(names):
            try:
                self._instances[name].start()
            except Exception:
                self.deactivate(self._active)
                raise
            self._active.add(name)

    def deactivate(self, names: set[str]) -> list[str]:
        """Stop the fixtures used by a testcase. Returns error messages, if any.

        The fixtures stay in the active set so the next testcase can decide
        whether they need a lazy_stop().
        """
        errors = []
        for name in reversed(self._ordered(names)):
            try:
                self._instances[name].stop()
            except Exception as exc:
                logger.exception("Fixture %r failed to stop", name)
                errors.append(f"fixture {name!r} stop() failed: {exc}")
        return errors

    def teardown_all(self) -> None:
        """Disconnect and tear down every created fixture, newest first."""
        names = list(reversed(self._instances))
        for name in self._ordered(self._active):
            self._call(name, "lazy_stop")
        self._active = set()
        for name in names:
            self._call(name, "disconnect")
        for name in names:
            self._call(name, "teardown")
        self._instances.clear()

    def _check_reference(self, value: Any, hint: type) -> str:
        if not isinstance(value, str):
            raise FixtureError(
                f"A {hint.__qualname__} parameter must name a configured fixture, got {value!r}"
            )
        if value not in self._entries:
            known = ", ".join(sorted(self._entries)) or "none"
            raise FixtureError(f"No fixture named {value!r} is configured (known: {known})")
        return value

    def _create(self, entry: FixtureEntry) -> Fixture:
        cls = load_class(entry.cls)
        if not issubclass(cls, Fixture):
            raise FixtureError(f"{entry.cls!r} is not a subclass of fixturerig.base.Fixture")
        kwargs = map_config_to_method_args(entry, cls, self.resolver(set()))
        logger.info("Set up fixture %s (%s)", entry.name, entry.cls)
        instance = cls(**kwargs)
        instance.setup()
        if not instance.self_test():
            # Leave the hardware in a safe state before reporting it broken.
            for hook in ("disconnect", "teardown"):
                try:
                    getattr(instance, hook)()
                except Exception:
                    logger.exception("Fixture %r failed in %s() after a failed self test", entry.name, hook)
            raise FixtureError(f"Fixture {entry.name!r} failed its self test")
        return instance

    def _ordered(self, names: set[str]) -> list[str]:
        return [name for name in self._instances if name in names]

    def _call(self, name: str, hook: str) -> None:
        try:
            getattr(self._instances[name], hook)()
        except Exception:
            logger.exception("Fixture %r failed in %s()", name, hook)


def run_test(
    test: TestCaseEntry,
    fixtures: FixtureManager,
    stream: ReportStream | None = None,
) -> TestResult:
    """Run a single configured testcase through its full lifecycle.

    Loads and instantiates the testcase class (resolving fixture references
    through `fixtures`), starts the fixtures it uses, then calls
    setup() / test() / teardown() and classifies the outcome into a Verdict.
    Never raises for test, configuration or fixture problems; those are
    reported in the returned TestResult and as a TestFinished event on
    `stream` (a stream without modules if none is given).
    """
    stream = stream if stream is not None else ReportStream()
    with stream.activate():
        return _run_test(test, fixtures, stream)


def _run_test(test: TestCaseEntry, fixtures: FixtureManager, stream: ReportStream) -> TestResult:
    logger.debug("Run test %s", test.name)
    start_time = time.perf_counter()

    try:
        cls = load_class(test.cls)
    except ClassLoadError as exc:
        cls, load_error = None, exc
    else:
        load_error = None
    stream.emit(
        TestStarted(
            name=test.name,
            cls=test.cls,
            description=_description(cls),
            params=dict(test.params),
            traceability=list(test.traceability),
        )
    )

    def result(verdict: Verdict) -> TestResult:
        duration = time.perf_counter() - start_time
        logger.debug("Test %s: %s (%.3fs)", test.name, verdict, duration)
        stream.emit(
            TestFinished(
                name=test.name,
                verdict=verdict,
                duration=duration,
                traceability=list(test.traceability),
            )
        )
        return TestResult(test.name, verdict, duration)

    used: set[str] = set()
    try:
        if load_error is not None:
            raise load_error
        kwargs = map_config_to_method_args(test, cls, fixtures.resolver(used))
    except (ClassLoadError, ArgumentMappingError, FixtureError) as exc:
        logger.error("Test %s skipped: %s", test.name, exc)
        return result(Verdict(VerdictStatus.SKIPPED, str(exc)))

    if not callable(getattr(cls, "test", None)):
        return result(Verdict(VerdictStatus.SKIPPED, f"{test.cls!r} has no test() method"))

    try:
        instance = cls(**kwargs)
    except Exception as exc:
        logger.exception("Test %s could not be instantiated", test.name)
        return result(Verdict(VerdictStatus.ERROR, f"{test.cls}() raised {exc!r}"))

    try:
        fixtures.activate(used)
    except Exception as exc:
        logger.exception("Test %s skipped: a fixture failed to start", test.name)
        return result(Verdict(VerdictStatus.SKIPPED, f"fixture start() failed: {exc}"))

    verdict = _with_reported(_execute(instance, test.name), stream)

    cleanup_errors = []
    if hasattr(instance, "teardown"):
        try:
            instance.teardown()
        except Exception as exc:
            logger.exception("Test %s failed in teardown()", test.name)
            cleanup_errors.append(f"teardown() raised {exc!r}")
    cleanup_errors.extend(fixtures.deactivate(used))

    if cleanup_errors and verdict.passed:
        verdict = Verdict(VerdictStatus.ERROR, "; ".join(cleanup_errors))
    return result(verdict)


def _description(cls: type | None) -> str:
    """The test class's own docstring, used as its specification text.

    Inherited docstrings (e.g. of base.TestCase) are deliberately ignored.
    """
    doc = cls.__dict__.get("__doc__") if cls is not None else None
    return inspect.cleandoc(doc) if isinstance(doc, str) else ""


def _with_reported(verdict: Verdict, stream: ReportStream) -> Verdict:
    """Downgrade a PASSED verdict to FAILED if the test reported a failed check."""
    if not verdict.passed:
        return verdict
    failed = [v for v in stream.reported_verdicts() if v.status is VerdictStatus.FAILED]
    if not failed:
        return verdict
    messages = [v.message for v in failed if v.message]
    summary = f"{len(failed)} reported check(s) failed"
    return Verdict(VerdictStatus.FAILED, f"{summary}: {'; '.join(messages)}" if messages else summary)


def _execute(instance: Any, name: str) -> Verdict:
    """Call setup() and test() on a testcase instance and classify the outcome."""
    try:
        if hasattr(instance, "setup"):
            instance.setup()
        outcome = instance.test()
    except VerdictException as exc:
        return _classify(exc.verdict)
    except Exception as exc:
        logger.exception("Test %s raised an exception", name)
        return Verdict(VerdictStatus.ERROR, f"{type(exc).__name__}: {exc}")
    return _classify(outcome)


def _classify(outcome: Any) -> Verdict:
    if outcome is None:
        return Verdict(VerdictStatus.NONE, "test() returned no verdict")
    if isinstance(outcome, bool):
        return Verdict(outcome)
    if isinstance(outcome, Verdict):
        if outcome.status in _TEST_SETTABLE:
            return outcome
        return Verdict(
            VerdictStatus.ERROR,
            f"test() reported {outcome.status.value!r}, which only the runner may set",
        )
    return Verdict(
        VerdictStatus.ERROR,
        f"test() returned {type(outcome).__name__}; expected bool or Verdict",
    )


def run_tests(config: Config, report_stream: ReportStream | None = None) -> list[TestResult]:
    """Run every configured testcase in configuration order and return the results.

    Everything the run and its tests report goes to `report_stream`. The
    caller owns the stream and closes it (see main.py); without one the run
    reports into a stream that has no modules.
    """
    stream = report_stream if report_stream is not None else ReportStream()
    fixtures = FixtureManager(config)
    results: list[TestResult] = []
    start_time = time.perf_counter()
    with stream.activate():
        stream.emit(RunStarted())
        try:
            _run_entries(config.entries, fixtures, stream, results)
        finally:
            fixtures.teardown_all()
            counts: dict[str, int] = {}
            for r in results:
                counts[r.verdict.status.value] = counts.get(r.verdict.status.value, 0) + 1
            stream.emit(RunFinished(counts=counts, duration=time.perf_counter() - start_time))

    passed = sum(1 for r in results if r.passed)
    logger.info("%d of %d test(s) passed", passed, len(results))
    return results


def _run_entries(entries, fixtures: FixtureManager, stream: ReportStream, results: list[TestResult]) -> None:
    """Run the testcases in `entries` depth first, reporting group boundaries."""
    for entry in entries:
        if isinstance(entry, TestCaseEntry):
            results.append(_run_test(entry, fixtures, stream))
        elif isinstance(entry, TestGroup):
            start_time = time.perf_counter()
            stream.emit(GroupStarted(name=entry.name))
            try:
                _run_entries(entry.entries, fixtures, stream, results)
            finally:
                stream.emit(GroupFinished(name=entry.name, duration=time.perf_counter() - start_time))
