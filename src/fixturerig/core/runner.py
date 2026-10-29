#
# This module handles everything related to the execution logic and order of the tests
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Execution
# Model", "Base classes" and "Design Constraints and Open Decisions"):
#
# - Tests run strictly in configuration order (a depth first walk of the
#   config tree, i.e. the order of Config.testcases()). There is no
#   reordering or parallelism. option_only entries (see config/model.py) are
#   skipped, like Config.testcases() skips them.
#
# - A testcase parameter whose type hint is a base.Fixture subclass is a
#   reference to a configured fixture *by name*: the config value must be the
#   `name` of a `fixture` entry. This is the smallest coherent answer to
#   "What syntax identifies a reference to another fixture?" and is enforced
#   only through type hints, so plain string parameters are never mistaken
#   for references. A required fixture parameter the config does not name is
#   resolved by its own parameter name; a testcase `fixturemap` maps a
#   parameter to a fixture with a different name (see core/inheritance.py).
#
# - A testcase's config params are mapped onto the parameters of its
#   __init__, setup(), test() and teardown() together (see
#   map_config_to_methods in fixturerig.core.inheritance). Each method gets
#   the params it names, so setup() and test() may both receive the same
#   fixture or value; a param no method takes is an error. Fixtures are
#   configured through __init__ only.
#
# - Fixtures are instantiated lazily, on first reference, and then shared by
#   every later testcase (and fixture) that references the same name. On
#   creation a fixture gets `setup()` and `self_test()`. A fixture that fails
#   either is remembered as broken, so later tests that need it are skipped
#   immediately instead of retrying the hardware.
#
# - Autoloaded fixtures (`autoloaded: true`) are the exception to lazy
#   creation: run_tests creates them, in configuration order, right at the
#   start of the run - before any other entry (including the env_setup
#   steps) is executed. After that they behave as if every
#   testcase required them under their configured name: they are started and
#   stopped around every testcase, and a broken autoloaded fixture skips
#   every testcase. A testcase may still name one explicitly to get a
#   reference to it; nothing else changes.
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
#     * a FAILED verdict the test reported through report.verdict() /
#       report.check() turns an otherwise PASSED result into FAILED, so a
#       test can record several checks and still return True at the end.
#
# - Reporting (see fixturerig.report): the run reports into one ReportStream,
#   which is activated for the whole run so `report` inside tests and
#   fixtures reaches it. The runner reports RunStarted/RunFinished around the
#   run, GroupStarted/GroupFinished around every test group, and
#   TestStarted/TestFinished around every testcase - also for testcases that
#   are skipped before they run. TestStarted carries the test specification:
#   class, class docstring, configured params and traceability IDs.
#
# - Each phase of a run is its own function, so main.py (or a host system)
#   calls them one by one inside a RunSession, which holds the state they
#   share: the fixtures, the setup failure and the results. RunSession
#   reports RunStarted/RunFinished and creates/tears down the fixtures;
#   run_all() runs every phase in order in one call.
#
# - Generators (see core/generator.py) are expanded by the run_generators
#   phase, the first one: right after the autoloaded fixtures are created
#   and before any step runs, so a broken generator stops the run before
#   the rig is touched. run_tests only runs tests; it refuses to run while a
#   generator has not run yet, rather than silently leaving out the tests it
#   would generate. The runner then treats a
#   Generator node like an anonymous group: it runs the generated entries in
#   place and reports no group boundaries of its own - unless create_group is
#   off, the generated entries are already wrapped in a TestGroup, which is
#   reported as usual.
#
# - The phases run in this order: autoloaded fixtures, generators, env_setup,
#   dut_info, tests, dut_shutdown, fixture teardown. Lifecycle steps
#   (config.model.Step, base.Step) run in configuration order within their
#   stage. A step's params are mapped onto its __init__ and run() together,
#   like a testcase's; fixture references work as for testcases, and the
#   referenced fixtures are start()ed before run() and stop()ped after it.
#
# - The first env_setup / dut_info step that fails (class loading, argument
#   mapping, a fixture problem, an exception or an invalid return value) ends
#   the setup: the remaining setup steps don't run and
#   every testcase is reported SKIPPED with the reason, since tests on an
#   unprepared rig or DUT are meaningless. The dut_shutdown steps always run,
#   all of them, even after a failed setup, an earlier failed shutdown step
#   or an aborted run, so the DUT is left in a safe state. A failed shutdown
#   step is logged and reported but does not change any test verdict.
#
# - Steps are not tests: they are not counted in RunFinished. Each step is
#   reported as a group named "<stage>: <name>", so what it reports through
#   `report` and the mapping its run() returns (as a two column table) show
#   up in every report module. A failed step adds an ERROR VerdictEvent with
#   the reason to its group.
#
# - Interactive mode (`--interactive`, RunSession(interactive=True)) is for
#   debugging and test development: an exception raised by test, fixture,
#   step or generator code is not turned into a verdict or a failed step but
#   re-raised as it is, so it ends the program and an IDE can break on it.
#   Configuration problems (class loading, argument mapping, unknown or
#   broken fixtures, a failed self test) are still reported as usual. The
#   cleanup still runs on the way out - dut_shutdown steps, fixture teardown
#   and the reports - and stays non-raising, so the DUT is left in a safe
#   state and the original exception reaches the top unchanged.
#

from __future__ import annotations

import logging
import time
import inspect
from dataclasses import dataclass
from typing import Any, Mapping

from fixturerig.base.fixture import Fixture
from fixturerig.base.step import Step as BaseStep
from fixturerig.base.verdict import Verdict, VerdictException, VerdictStatus
from fixturerig.config.model import Config, ConfigError, is_active
from fixturerig.config.model import Fixture as FixtureEntry
from fixturerig.config.model import Generator as GeneratorEntry
from fixturerig.config.model import Step as StepEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.config.model import TestGroup
from fixturerig.core.class_loader import ClassLoadError, load_class
from fixturerig.core.generator import expand_generators
from fixturerig.core.inheritance import ArgumentMappingError, map_config_to_method_args, map_config_to_methods
from fixturerig.report.elements import Table
from fixturerig.report.events import (
    GroupFinished,
    GroupStarted,
    RunFinished,
    RunStarted,
    TableEvent,
    TestFinished,
    TestStarted,
    VerdictEvent,
)
from fixturerig.report.stream import ReportStream

logger = logging.getLogger(__name__)

# Testcase methods whose parameters are filled from config, besides __init__.
_TEST_METHODS = ("setup", "test", "teardown")

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

    def __init__(self, config: Config, interactive: bool = False):
        # Re-raise exceptions from test, fixture and step code (see "Interactive mode").
        self.interactive = interactive
        self._entries: dict[str, FixtureEntry] = {}
        for entry in config.fixtures():
            if entry.name in self._entries:
                raise ConfigError(f"Fixture {entry.name!r} is configured more than once")
            self._entries[entry.name] = entry
        self._autoloaded = [name for name, entry in self._entries.items() if entry.autoloaded]
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

    def load_autoloaded(self) -> None:
        """Create every autoloaded fixture, in configuration order.

        A fixture that cannot be created is logged and remembered as broken;
        require_autoloaded() then skips every testcase.
        """
        for name in self._autoloaded:
            try:
                self.get(name)
            except FixtureError:
                logger.exception("Autoloaded fixture %r is unavailable", name)

    def require_autoloaded(self, used: set[str]) -> None:
        """Add every autoloaded fixture to `used`, as if the testcase had required it.

        :raises FixtureError: if an autoloaded fixture is unavailable.
        """
        for name in self._autoloaded:
            self.get(name)
            used.add(name)

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
            if isinstance(exc, FixtureError) or self.interactive:
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
            self._call(name, "lazy_stop", reraise=self.interactive)
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
                if self.interactive:
                    raise
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

    def _call(self, name: str, hook: str, reraise: bool = False) -> None:
        try:
            getattr(self._instances[name], hook)()
        except Exception:
            if reraise:
                raise
            logger.exception("Fixture %r failed in %s()", name, hook)


def run_test(
    test: TestCaseEntry,
    fixtures: FixtureManager,
    stream: ReportStream | None = None,
) -> TestResult:
    """Run a single configured testcase through its full lifecycle.

    Loads and instantiates the testcase class (resolving fixture references
    through `fixtures`), starts the fixtures it uses, then calls
    setup() / test() / teardown() - each with the config params it names -
    and classifies the outcome into a Verdict.
    Never raises for test, configuration or fixture problems; those are
    reported in the returned TestResult and as a TestFinished event on
    `stream` (a stream without modules if none is given).
    """
    stream = stream if stream is not None else ReportStream()
    with stream.activate():
        return _run_test(test, fixtures, stream)


def _run_test(
    test: TestCaseEntry,
    fixtures: FixtureManager,
    stream: ReportStream,
    skip_reason: str | None = None,
) -> TestResult:
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

    if skip_reason is not None:
        logger.error("Test %s skipped: %s", test.name, skip_reason)
        return result(Verdict(VerdictStatus.SKIPPED, skip_reason))

    if load_error is None and not callable(getattr(cls, "test", None)):
        return result(Verdict(VerdictStatus.SKIPPED, f"{test.cls!r} has no test() method"))

    used: set[str] = set()
    try:
        if load_error is not None:
            raise load_error
        fixtures.require_autoloaded(used)
        methods = [name for name in _TEST_METHODS if callable(getattr(cls, name, None))]
        init_kwargs, *method_kwargs = map_config_to_methods(
            test, [cls, *(getattr(cls, name) for name in methods)], fixtures.resolver(used)
        )
    except (ClassLoadError, ArgumentMappingError, FixtureError) as exc:
        logger.error("Test %s skipped: %s", test.name, exc)
        return result(Verdict(VerdictStatus.SKIPPED, str(exc)))
    kwargs = dict(zip(methods, method_kwargs))

    try:
        instance = cls(**init_kwargs)
    except Exception as exc:
        if fixtures.interactive:
            raise
        logger.exception("Test %s could not be instantiated", test.name)
        return result(Verdict(VerdictStatus.ERROR, f"{test.cls}() raised {exc!r}"))

    try:
        fixtures.activate(used)
    except Exception as exc:
        if fixtures.interactive:
            raise
        logger.exception("Test %s skipped: a fixture failed to start", test.name)
        return result(Verdict(VerdictStatus.SKIPPED, f"fixture start() failed: {exc}"))

    verdict = _with_reported(_execute(instance, test.name, kwargs, fixtures.interactive), stream)

    cleanup_errors = []
    if "teardown" in kwargs:
        try:
            instance.teardown(**kwargs["teardown"])
        except Exception as exc:
            if fixtures.interactive:
                raise
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


def _execute(instance: Any, name: str, kwargs: dict[str, dict[str, Any]], interactive: bool = False) -> Verdict:
    """Call setup() and test() on a testcase instance and classify the outcome.

    `kwargs` holds the mapped config params per method name. In interactive
    mode an exception other than VerdictException is re-raised.
    """
    try:
        if "setup" in kwargs:
            instance.setup(**kwargs["setup"])
        outcome = instance.test(**kwargs["test"])
    except VerdictException as exc:
        return _classify(exc.verdict)
    except Exception as exc:
        if interactive:
            raise
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


class RunSession:
    """The state the phases of one run share: config, report stream, fixtures and results.

    Use it as a context manager around the phases. Entering activates the
    report stream (so `report` reaches it), reports RunStarted and creates the
    autoloaded fixtures. Leaving - also when a phase raises - tears down every
    fixture and reports RunFinished with the verdict counts of all tests run.

    Without a `report_stream` the run reports into a stream with no modules.
    The caller owns the stream and closes it (see main.py).

    With `interactive` an exception from test, fixture, step or generator
    code ends the run and propagates to the caller (see "Interactive mode").
    """

    def __init__(self, config: Config, report_stream: ReportStream | None = None, interactive: bool = False):
        self.config = config
        self.stream = report_stream if report_stream is not None else ReportStream()
        self.interactive = interactive
        self.fixtures = FixtureManager(config, interactive)
        self.results: list[TestResult] = []
        # Why the tests are skipped, once a setup step has failed.
        self.setup_failure: str | None = None
        self._activation: Any = None
        self._start_time = 0.0

    def __enter__(self) -> RunSession:
        self._activation = self.stream.activate()
        self._activation.__enter__()
        self._start_time = time.perf_counter()
        self.stream.emit(RunStarted())
        try:
            self.fixtures.load_autoloaded()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *exc_info) -> None:
        try:
            self.fixtures.teardown_all()
            counts: dict[str, int] = {}
            for r in self.results:
                counts[r.verdict.status.value] = counts.get(r.verdict.status.value, 0) + 1
            self.stream.emit(RunFinished(counts=counts, duration=time.perf_counter() - self._start_time))
        finally:
            self._activation.__exit__(None, None, None)
        passed = sum(1 for r in self.results if r.passed)
        logger.info("%d of %d test(s) passed", passed, len(self.results))


def run_env_setup(session: RunSession) -> None:
    """Run the env_setup steps (see _run_setup_stage)."""
    _run_setup_stage(session, "env_setup")


def run_dut_info(session: RunSession) -> None:
    """Run the dut_info steps (see _run_setup_stage)."""
    _run_setup_stage(session, "dut_info")


def run_dut_shutdown(session: RunSession) -> None:
    """Run every dut_shutdown step, whatever happened before or in an earlier step."""
    for step in session.config.steps("dut_shutdown"):
        _run_step(step, session.fixtures, session.stream, cleanup=True)


def run_generators(session: RunSession) -> None:
    """Expand every generator that has not run yet (see core/generator.py).

    Runs inside the session, so generate() can use `report`.

    :raises GeneratorError: if a generator fails; it is a ConfigError.
    """
    expand_generators(session.config, session.interactive)


def run_tests(session: RunSession) -> list[TestResult]:
    """Run every configured testcase in configuration order and return the results.

    Only the tests: the generators must have run already (see run_generators).
    After a failed setup step every testcase is reported SKIPPED. The results
    are also added to `session.results`.

    :raises ConfigError: if a generator has not run yet.
    """
    pending = [g.name for g in session.config.generators() if not g.generated]
    if pending:
        raise ConfigError(f"Generator(s) {pending} have not run; call run_generators() before run_tests()")
    results: list[TestResult] = []
    try:
        _run_entries(session.config.entries, session.fixtures, session.stream, results, session.setup_failure)
    finally:
        # Keep the results of the tests that ran, also when an interactive run ends early.
        session.results.extend(results)
    return results


def run_all(
    config: Config, report_stream: ReportStream | None = None, interactive: bool = False
) -> list[TestResult]:
    """Run the whole lifecycle in one call, as main.py does, and return the test results.

    Order: autoloaded fixtures, generators, env_setup, dut_info, tests,
    dut_shutdown, fixture teardown.
    """
    with RunSession(config, report_stream, interactive) as session:
        try:
            run_generators(session)
            run_env_setup(session)
            run_dut_info(session)
            run_tests(session)
        finally:
            run_dut_shutdown(session)
    return session.results


def _run_setup_stage(session: RunSession, stage: str) -> None:
    """Run the steps of a setup stage until one fails.

    Does nothing once a setup step has failed; the first failure is recorded
    in `session.setup_failure`.
    """
    for step in session.config.steps(stage):
        if session.setup_failure is not None:
            return
        error = _run_step(step, session.fixtures, session.stream)
        if error is not None:
            session.setup_failure = f"{stage} step {step.name!r} failed: {error}"


def _run_step(step: StepEntry, fixtures: FixtureManager, stream: ReportStream, cleanup: bool = False) -> str | None:
    """Run one lifecycle step, reported as a group of its own.

    Never raises for step, configuration or fixture problems - except, in
    interactive mode, for an exception from the step's own code, unless it
    is a `cleanup` (dut_shutdown) step.

    :return: None on success, else the error message.
    """
    label = f"{step.stage}: {step.name}"
    logger.info("Run %s (%s)", label, step.cls)
    start_time = time.perf_counter()
    stream.emit(GroupStarted(name=label))
    try:
        error = _execute_step(step, fixtures, stream, fixtures.interactive and not cleanup)
        if error is not None:
            logger.error("%s failed: %s", label, error)
            stream.emit(VerdictEvent(Verdict(VerdictStatus.ERROR, error)))
    finally:
        stream.emit(GroupFinished(name=label, duration=time.perf_counter() - start_time))
    return error


def _execute_step(step: StepEntry, fixtures: FixtureManager, stream: ReportStream, interactive: bool) -> str | None:
    used: set[str] = set()
    try:
        cls = load_class(step.cls)
        if not issubclass(cls, BaseStep):
            return f"{step.cls!r} is not a subclass of fixturerig.base.Step"
        init_kwargs, run_kwargs = map_config_to_methods(step, [cls, cls.run], fixtures.resolver(used))
    except (ClassLoadError, ArgumentMappingError, FixtureError) as exc:
        return str(exc)

    try:
        instance = cls(**init_kwargs)
    except Exception as exc:
        if interactive:
            raise
        logger.exception("Step %s could not be instantiated", step.name)
        return f"{step.cls}() raised {exc!r}"

    try:
        fixtures.activate(used)
    except Exception as exc:
        if interactive:
            raise
        logger.exception("Step %s: a fixture failed to start", step.name)
        return f"fixture start() failed: {exc}"

    try:
        info = instance.run(**run_kwargs)
    except Exception as exc:
        if interactive:
            raise
        logger.exception("Step %s raised an exception", step.name)
        error = f"{type(exc).__name__}: {exc}"
    else:
        error = _report_info(info, step, stream)

    stop_errors = fixtures.deactivate(used)
    if error is None and stop_errors:
        error = "; ".join(stop_errors)
    return error


def _report_info(info: Any, step: StepEntry, stream: ReportStream) -> str | None:
    """Report the mapping a step's run() returned as a table. Returns an error for anything else."""
    if info is None:
        return None
    if not isinstance(info, Mapping):
        return f"run() returned {type(info).__name__}; expected a mapping or None"
    rows = [
        [str(key), value if isinstance(value, (str, int, float, bool, type(None))) else str(value)]
        for key, value in info.items()
    ]
    stream.emit(TableEvent(Table(rows, headers=["Name", "Value"], title=step.name)))
    return None


def _run_entries(
    entries,
    fixtures: FixtureManager,
    stream: ReportStream,
    results: list[TestResult],
    skip_reason: str | None = None,
) -> None:
    """Run the testcases in `entries` depth first, reporting group boundaries.

    With a `skip_reason`, every testcase is reported SKIPPED without running.
    """
    for entry in entries:
        if not is_active(entry):
            continue
        if isinstance(entry, TestCaseEntry):
            results.append(_run_test(entry, fixtures, stream, skip_reason))
        elif isinstance(entry, GeneratorEntry):
            _run_entries(entry.entries, fixtures, stream, results, skip_reason)
        elif isinstance(entry, TestGroup):
            start_time = time.perf_counter()
            stream.emit(GroupStarted(name=entry.name))
            try:
                _run_entries(entry.entries, fixtures, stream, results, skip_reason)
            finally:
                stream.emit(GroupFinished(name=entry.name, duration=time.perf_counter() - start_time))
