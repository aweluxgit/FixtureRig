import pytest

from fixturerig.base import Fixture, Verdict, VerdictException, VerdictStatus
from fixturerig.base import TestCase as BaseTestCase  # aliased so pytest does not collect it
from fixturerig.config.model import Config, ConfigError
from fixturerig.config.model import Fixture as FixtureEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.config.model import TestGroup
from fixturerig.core.runner import FixtureManager, run_all, run_test
from fixturerig.report import ReportModule, ReportStream, current_stream, report

CALLS: list[str] = []


@pytest.fixture(autouse=True)
def _reset_calls():
    CALLS.clear()


def cls_path(cls: type) -> str:
    return f"{__name__}.{cls.__name__}"


# --- test doubles, loaded by dotted name ------------------------------------


class Psu(Fixture):
    def __init__(self, port: str = "COM1", healthy: bool = True):
        self.port = port
        self.healthy = healthy

    def setup(self):
        CALLS.append(f"psu.setup:{self.port}")

    def self_test(self):
        CALLS.append("psu.self_test")
        return self.healthy

    def start(self):
        CALLS.append("psu.start")

    def stop(self):
        CALLS.append("psu.stop")

    def lazy_stop(self):
        CALLS.append("psu.lazy_stop")

    def disconnect(self):
        CALLS.append("psu.disconnect")

    def teardown(self):
        CALLS.append("psu.teardown")


class LimitTest(BaseTestCase):
    def __init__(self, power_supply: Psu, limit: float, value: float = 1.0):
        self.power_supply = power_supply
        self.limit = limit
        self.value = value

    def setup(self):
        CALLS.append("test.setup")

    def test(self):
        CALLS.append("test.test")
        return self.value <= self.limit

    def teardown(self):
        CALLS.append("test.teardown")


class NoFixtureTest(BaseTestCase):
    def test(self):
        CALLS.append("nofixture.test")
        return True


class ReturnsVerdict(BaseTestCase):
    def __init__(self, status: str):
        self.status = status

    def test(self):
        return Verdict(self.status, "msg")


class RaisesVerdict(BaseTestCase):
    def test(self):
        raise VerdictException(False, "over limit")


class Crashes(BaseTestCase):
    def test(self):
        raise RuntimeError("boom")


class ReturnsNothing(BaseTestCase):
    def test(self):
        pass


class BadTeardown(BaseTestCase):
    def test(self):
        return True

    def teardown(self):
        raise RuntimeError("cleanup failed")


def make_config(*entries) -> Config:
    return Config(entries=list(entries))


def psu_entry(**params) -> FixtureEntry:
    return FixtureEntry(name="psu", cls=cls_path(Psu), params=params)


def limit_test(name="t", **params) -> TestCaseEntry:
    return TestCaseEntry(name=name, cls=cls_path(LimitTest), params={"power_supply": "psu", **params})


# --- run_test: lifecycle ----------------------------------------------------


def test_run_test_full_lifecycle_and_pass():
    config = make_config(psu_entry(port="COM4"), limit_test(limit=4.5))
    manager = FixtureManager(config)

    result = run_test(config.testcases()[0], manager)

    assert result.verdict.status is VerdictStatus.PASSED
    assert result.duration >= 0
    assert CALLS == [
        "psu.setup:COM4",
        "psu.self_test",
        "psu.start",
        "test.setup",
        "test.test",
        "test.teardown",
        "psu.stop",
    ]


def test_run_test_false_is_failed():
    config = make_config(psu_entry(), limit_test(limit=0.5))
    result = run_test(config.testcases()[0], FixtureManager(config))
    assert result.verdict.status is VerdictStatus.FAILED


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("passed", VerdictStatus.PASSED),
        ("failed", VerdictStatus.FAILED),
        ("skipped", VerdictStatus.SKIPPED),
        ("error", VerdictStatus.ERROR),
        ("none", VerdictStatus.ERROR),
        ("knownfailed", VerdictStatus.ERROR),
    ],
)
def test_run_test_returned_verdict(status, expected):
    entry = TestCaseEntry(name="v", cls=cls_path(ReturnsVerdict), params={"status": status})
    result = run_test(entry, FixtureManager(make_config()))
    assert result.verdict.status is expected


def test_run_test_verdict_exception():
    entry = TestCaseEntry(name="v", cls=cls_path(RaisesVerdict))
    result = run_test(entry, FixtureManager(make_config()))
    assert result.verdict == Verdict(VerdictStatus.FAILED, "over limit")


def test_run_test_exception_is_error():
    entry = TestCaseEntry(name="c", cls=cls_path(Crashes))
    result = run_test(entry, FixtureManager(make_config()))
    assert result.verdict.status is VerdictStatus.ERROR
    assert "boom" in result.verdict.message


def test_run_test_no_return_is_none():
    entry = TestCaseEntry(name="n", cls=cls_path(ReturnsNothing))
    result = run_test(entry, FixtureManager(make_config()))
    assert result.verdict.status is VerdictStatus.NONE


def test_run_test_teardown_error_turns_pass_into_error():
    entry = TestCaseEntry(name="b", cls=cls_path(BadTeardown))
    result = run_test(entry, FixtureManager(make_config()))
    assert result.verdict.status is VerdictStatus.ERROR
    assert "cleanup failed" in result.verdict.message


# --- run_test: configuration and fixture problems are skips ------------------


@pytest.mark.parametrize(
    "entry",
    [
        TestCaseEntry(name="x", cls="no.such.module.Test"),
        TestCaseEntry(name="x", cls=cls_path(LimitTest), params={"power_supply": "psu"}),  # missing limit
        TestCaseEntry(name="x", cls=cls_path(NoFixtureTest), params={"typo": 1}),
        TestCaseEntry(name="x", cls=cls_path(LimitTest), params={"power_supply": "nope", "limit": 1}),
    ],
)
def test_run_test_config_problems_are_skipped(entry):
    result = run_test(entry, FixtureManager(make_config(psu_entry())))
    assert result.verdict.status is VerdictStatus.SKIPPED


def test_failed_self_test_skips_and_is_not_retried():
    config = make_config(psu_entry(healthy=False), limit_test("a", limit=5), limit_test("b", limit=5))
    manager = FixtureManager(config)

    results = [run_test(t, manager) for t in config.testcases()]

    assert [r.verdict.status for r in results] == [VerdictStatus.SKIPPED] * 2
    assert "self test" in results[1].verdict.message
    assert CALLS.count("psu.self_test") == 1
    assert "test.test" not in CALLS


def test_duplicate_fixture_names_are_config_errors():
    with pytest.raises(ConfigError):
        FixtureManager(make_config(psu_entry(), psu_entry()))


# --- run_all: ordering and fixture sharing --------------------------------


def test_run_tests_shares_fixture_lazy_stops_and_tears_down():
    config = make_config(
        psu_entry(),
        TestGroup(entries=[limit_test("a", limit=5), limit_test("b", limit=5)]),
        TestCaseEntry(name="c", cls=cls_path(NoFixtureTest)),
    )

    results = run_all(config)

    assert [r.name for r in results] == ["a", "b", "c"]
    assert all(r.passed for r in results)
    assert CALLS.count("psu.setup:COM1") == 1
    assert CALLS[-5:] == ["psu.stop", "psu.lazy_stop", "nofixture.test", "psu.disconnect", "psu.teardown"]


def test_run_tests_unused_fixture_is_never_created():
    results = run_all(make_config(psu_entry(), TestCaseEntry(name="c", cls=cls_path(NoFixtureTest))))
    assert results[0].passed
    assert CALLS == ["nofixture.test"]



# --- autoloaded fixtures -------------------------------------------------------


def autoloaded_psu(**params) -> FixtureEntry:
    return FixtureEntry(name="psu", cls=cls_path(Psu), params=params, autoloaded=True)


def test_autoloaded_fixture_is_created_before_the_first_test():
    run_all(make_config(TestCaseEntry(name="c", cls=cls_path(NoFixtureTest)), autoloaded_psu()))
    assert CALLS[:3] == ["psu.setup:COM1", "psu.self_test", "psu.start"]


def test_autoloaded_fixture_is_created_without_any_tests():
    run_all(make_config(autoloaded_psu()))
    assert CALLS == ["psu.setup:COM1", "psu.self_test", "psu.disconnect", "psu.teardown"]


def test_autoloaded_fixture_is_started_and_stopped_for_every_test():
    config = make_config(
        autoloaded_psu(),
        TestCaseEntry(name="a", cls=cls_path(NoFixtureTest)),
        limit_test("b", limit=5),
    )

    results = run_all(config)

    assert all(r.passed for r in results)
    assert CALLS == [
        "psu.setup:COM1",
        "psu.self_test",
        "psu.start",
        "nofixture.test",
        "psu.stop",
        "psu.start",
        "test.setup",
        "test.test",
        "test.teardown",
        "psu.stop",
        "psu.lazy_stop",
        "psu.disconnect",
        "psu.teardown",
    ]


def test_broken_autoloaded_fixture_skips_every_test():
    config = make_config(autoloaded_psu(healthy=False), TestCaseEntry(name="a", cls=cls_path(NoFixtureTest)))

    results = run_all(config)

    assert results[0].verdict.status is VerdictStatus.SKIPPED
    assert "self test" in results[0].verdict.message
    assert CALLS.count("psu.self_test") == 1
    assert "nofixture.test" not in CALLS


# --- reporting ---------------------------------------------------------------


class _Recorder(ReportModule):
    def __init__(self):
        super().__init__()
        self.events = []

    def on_event(self, event):
        self.events.append(event)


class Documented(BaseTestCase):
    """Checks the documented behavior.

    Second paragraph.
    """

    def test(self):
        report.text("measuring")
        report.check(True, "first check")
        return True


class SoftFails(BaseTestCase):
    def test(self):
        report.check(False, "U too high")
        report.check(False, "I too high")
        return True


class SoftFailsThenErrors(BaseTestCase):
    def test(self):
        report.check(False, "U too high")
        raise RuntimeError("boom")


def _events(config: Config) -> list:
    recorder = _Recorder()
    run_all(config, ReportStream([recorder]))
    return recorder.events


def test_run_tests_reports_run_groups_and_tests_in_order():
    config = make_config(
        TestGroup(
            name="outer",
            entries=[
                TestGroup(name="inner", entries=[TestCaseEntry(name="a", cls=cls_path(Documented))]),
                TestCaseEntry(name="b", cls=cls_path(NoFixtureTest)),
            ],
        ),
        TestCaseEntry(name="c", cls=cls_path(NoFixtureTest)),
    )

    events = _events(config)

    assert [(e.kind, e.path) for e in events] == [
        ("run_started", ()),
        ("group_started", ("outer",)),
        ("group_started", ("outer", "inner")),
        ("test_started", ("outer", "inner", "a")),
        ("text", ("outer", "inner", "a")),
        ("verdict", ("outer", "inner", "a")),
        ("test_finished", ("outer", "inner", "a")),
        ("group_finished", ("outer", "inner")),
        ("test_started", ("outer", "b")),
        ("test_finished", ("outer", "b")),
        ("group_finished", ("outer",)),
        ("test_started", ("c",)),
        ("test_finished", ("c",)),
        ("run_finished", ()),
    ]
    assert events[-1].counts == {"passed": 3}


def test_test_started_carries_the_test_specification():
    entry = TestCaseEntry(name="a", cls=cls_path(Documented), params={}, traceability=["REQ-7"])
    started, *_, finished = [e for e in _events(make_config(entry)) if e.kind.startswith("test_")]

    assert started.cls == cls_path(Documented)
    assert started.description == "Checks the documented behavior.\n\nSecond paragraph."
    assert started.traceability == ["REQ-7"]
    assert finished.verdict.passed
    assert finished.traceability == ["REQ-7"]


def test_inherited_docstring_is_not_a_description():
    started = next(e for e in _events(make_config(TestCaseEntry(name="n", cls=cls_path(NoFixtureTest)))) if e.kind == "test_started")
    assert started.description == ""


def test_skipped_tests_are_still_reported():
    events = _events(make_config(TestCaseEntry(name="x", cls="no.such.module.Test")))
    finished = next(e for e in events if e.kind == "test_finished")
    assert finished.verdict.status is VerdictStatus.SKIPPED
    assert "no.such.module" in finished.verdict.message


def test_reported_failed_check_fails_a_passing_test():
    result = run_test(TestCaseEntry(name="s", cls=cls_path(SoftFails)), FixtureManager(make_config()))
    assert result.verdict == Verdict(VerdictStatus.FAILED, "2 reported check(s) failed: U too high; I too high")


def test_reported_failed_check_keeps_a_worse_verdict():
    result = run_test(TestCaseEntry(name="s", cls=cls_path(SoftFailsThenErrors)), FixtureManager(make_config()))
    assert result.verdict.status is VerdictStatus.ERROR


def test_report_reaches_the_run_stream_from_inside_tests():
    recorder = _Recorder()
    stream = ReportStream([recorder])
    run_test(TestCaseEntry(name="a", cls=cls_path(Documented)), FixtureManager(make_config()), stream)
    assert [e.kind for e in recorder.events] == ["test_started", "text", "verdict", "test_finished"]
    assert current_stream() is not stream  # deactivated after the test


class Aborts(BaseTestCase):
    def test(self):
        raise KeyboardInterrupt


def test_run_finished_is_reported_when_the_run_aborts():
    recorder = _Recorder()
    with pytest.raises(KeyboardInterrupt):
        run_all(make_config(TestCaseEntry(name="a", cls=cls_path(Aborts))), ReportStream([recorder]))
    assert recorder.events[-1].kind == "run_finished"


class MethodParams(BaseTestCase):
    def setup(self, power_supply: Psu):
        CALLS.append(f"test.setup:{power_supply.port}")

    def test(self, power_supply: Psu, limit: float) -> bool:
        CALLS.append(f"test.test:{power_supply.port}")
        return limit > 1

    def teardown(self, power_supply: Psu):
        CALLS.append(f"test.teardown:{power_supply.port}")


def test_setup_test_and_teardown_get_their_config_params():
    entry = TestCaseEntry(name="m", cls=cls_path(MethodParams), params={"power_supply": "psu", "limit": 4.5})
    result = run_test(entry, FixtureManager(make_config(psu_entry(), entry)))

    assert result.verdict.status is VerdictStatus.PASSED
    assert CALLS == [
        "psu.setup:COM1",
        "psu.self_test",
        "psu.start",
        "test.setup:COM1",
        "test.test:COM1",
        "test.teardown:COM1",
        "psu.stop",
    ]


def test_param_no_method_takes_is_skipped():
    entry = TestCaseEntry(
        name="m", cls=cls_path(MethodParams), params={"power_supply": "psu", "limit": 4.5, "typo": 1}
    )
    result = run_test(entry, FixtureManager(make_config(psu_entry(), entry)))

    assert result.verdict.status is VerdictStatus.SKIPPED
    assert "typo" in result.verdict.message


# --- fixture references: by parameter name and through fixturemap ------------


class UsesPsuByName(BaseTestCase):
    def test(self, psu: Psu):
        CALLS.append(f"test.test:{psu.port}")
        return True


class OptionalPsu(BaseTestCase):
    def test(self, psu: Psu | None = None):
        CALLS.append(f"test.test:{psu}")
        return True


def test_fixture_param_without_config_resolves_by_its_name():
    entry = TestCaseEntry(name="n", cls=cls_path(UsesPsuByName))
    result = run_test(entry, FixtureManager(make_config(psu_entry(port="COM4"), entry)))

    assert result.verdict.status is VerdictStatus.PASSED
    assert "test.test:COM4" in CALLS
    assert CALLS[-1] == "psu.stop"


def test_fixture_param_without_matching_fixture_is_skipped():
    entry = TestCaseEntry(name="n", cls=cls_path(UsesPsuByName))
    result = run_test(entry, FixtureManager(make_config(entry)))

    assert result.verdict.status is VerdictStatus.SKIPPED
    assert "'psu'" in result.verdict.message


def test_fixture_param_with_default_keeps_its_default():
    entry = TestCaseEntry(name="n", cls=cls_path(OptionalPsu))
    result = run_test(entry, FixtureManager(make_config(psu_entry(), entry)))

    assert result.verdict.status is VerdictStatus.PASSED
    assert CALLS == ["test.test:None"]


def test_fixturemap_maps_param_to_differently_named_fixture():
    bench = FixtureEntry(name="psu_bench_2", cls=cls_path(Psu), params={"port": "COM7"})
    entry = TestCaseEntry(
        name="m",
        cls=cls_path(MethodParams),
        params={"limit": 4.5},
        fixturemap={"power_supply": "psu_bench_2"},
    )
    result = run_test(entry, FixtureManager(make_config(psu_entry(), bench, entry)))

    assert result.verdict.status is VerdictStatus.PASSED
    assert "test.test:COM7" in CALLS
    assert "psu.setup:COM1" not in CALLS


def test_fixturemap_overrides_a_default():
    entry = TestCaseEntry(name="n", cls=cls_path(OptionalPsu), fixturemap={"psu": "psu"})
    result = run_test(entry, FixtureManager(make_config(psu_entry(), entry)))

    assert result.verdict.status is VerdictStatus.PASSED
    assert "test.test:None" not in CALLS


@pytest.mark.parametrize(
    ("params", "fixturemap", "message"),
    [
        ({"power_supply": "psu"}, {"limit": "psu"}, "not a fixture parameter"),
        ({"power_supply": "psu", "limit": 4.5}, {"typo": "psu"}, "typo"),
        ({"limit": 4.5}, {"power_supply": "nope"}, "nope"),
    ],
)
def test_invalid_fixturemap_is_skipped(params, fixturemap, message):
    entry = TestCaseEntry(name="m", cls=cls_path(MethodParams), params=params, fixturemap=fixturemap)
    result = run_test(entry, FixtureManager(make_config(psu_entry(), entry)))

    assert result.verdict.status is VerdictStatus.SKIPPED
    assert message in result.verdict.message


# --- interactive mode --------------------------------------------------------


class CrashesInSetup(BaseTestCase):
    def setup(self):
        raise RuntimeError("setup boom")

    def test(self):
        return True


class CrashesInInit(BaseTestCase):
    def __init__(self):
        raise RuntimeError("init boom")

    def test(self):
        return True


class CrashingPsu(Psu):
    def setup(self):
        raise RuntimeError("psu boom")


class PsuFailsToStop(Psu):
    def stop(self):
        raise RuntimeError("stop boom")


@pytest.mark.parametrize(
    "cls, message",
    [(Crashes, "boom"), (CrashesInSetup, "setup boom"), (CrashesInInit, "init boom"), (BadTeardown, "cleanup failed")],
)
def test_interactive_test_exception_ends_the_run(cls, message):
    config = make_config(
        TestCaseEntry(name="crash", cls=cls_path(cls)),
        TestCaseEntry(name="after", cls=cls_path(NoFixtureTest)),
    )

    with pytest.raises(RuntimeError, match=message):
        run_all(config, interactive=True)

    assert "nofixture.test" not in CALLS


def test_interactive_fixture_exception_is_raised_as_it_is():
    config = make_config(FixtureEntry(name="psu", cls=cls_path(CrashingPsu)), limit_test(limit=4.5))

    with pytest.raises(RuntimeError, match="psu boom"):
        run_all(config, interactive=True)


def test_interactive_fixture_stop_exception_ends_the_run_after_teardown():
    config = make_config(FixtureEntry(name="psu", cls=cls_path(PsuFailsToStop)), limit_test(limit=4.5))

    with pytest.raises(RuntimeError, match="stop boom"):
        run_all(config, interactive=True)

    assert CALLS[-2:] == ["psu.disconnect", "psu.teardown"]


def test_interactive_still_reports_verdicts_and_config_problems():
    config = make_config(
        TestCaseEntry(name="raises_verdict", cls=cls_path(RaisesVerdict)),
        TestCaseEntry(name="unknown", cls="no.such.Module"),
        TestCaseEntry(name="ok", cls=cls_path(NoFixtureTest)),
    )

    results = run_all(config, interactive=True)

    assert [r.verdict.status for r in results] == [
        VerdictStatus.FAILED,
        VerdictStatus.SKIPPED,
        VerdictStatus.PASSED,
    ]
