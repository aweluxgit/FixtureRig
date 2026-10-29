from pathlib import Path

import pytest

from fixturerig.base import Fixture, Generator, Step, VerdictStatus
from fixturerig.base import TestCase as BaseTestCase  # aliased so pytest does not collect it
from fixturerig.config.model import Config, ConfigError, ConfigPath
from fixturerig.config.model import Fixture as FixtureEntry
from fixturerig.config.model import Generator as GeneratorEntry
from fixturerig.config.model import Step as StepEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.config.model import TestGroup
from fixturerig.core.runner import (
    RunSession,
    run_all,
    run_dut_info,
    run_dut_shutdown,
    run_env_setup,
    run_generators,
    run_tests,
)
from fixturerig.report import ReportModule, ReportStream, report

CALLS: list[str] = []


@pytest.fixture(autouse=True)
def _reset_calls():
    CALLS.clear()


def cls_path(cls: type) -> str:
    return f"{__name__}.{cls.__name__}"


def step(stage: str, cls: type, name: str | None = None, **params) -> StepEntry:
    return StepEntry(stage=stage, name=name or cls.__name__, cls=cls_path(cls), params=params)


def tc(name: str = "t") -> TestCaseEntry:
    return TestCaseEntry(name=name, cls=cls_path(Recorded))


# --- test doubles, loaded by dotted name ------------------------------------


class Dut(Fixture):
    def setup(self):
        CALLS.append("dut.setup")

    def start(self):
        CALLS.append("dut.start")

    def stop(self):
        CALLS.append("dut.stop")

    def lazy_stop(self):
        CALLS.append("dut.lazy_stop")

    def teardown(self):
        CALLS.append("dut.teardown")


class Recorded(BaseTestCase):
    def test(self):
        CALLS.append("test")
        return True


class Prepare(Step):
    def run(self):
        CALLS.append("env_setup")


class Flash(Step):
    def __init__(self, image: Path):
        self.image = image

    def run(self, dut: Dut, retries: int = 1):
        CALLS.append(f"flash:{self.image.name}:{retries}")


class Collect(Step):
    def run(self):
        CALLS.append("dut_info")
        report.text("collecting")
        return {"serial": "SN-1", "version": 3, "path": Path("fw.bin")}


class PowerOff(Step):
    def run(self):
        CALLS.append("dut_shutdown")


class Fails(Step):
    def run(self):
        CALLS.append("fails")
        raise RuntimeError("no power")


class ReturnsList(Step):
    def run(self):
        return ["serial"]


class NotAStep:
    def run(self):
        CALLS.append("not_a_step")


class Gen(Generator):
    def generate(self):
        CALLS.append("generate")
        return [tc("generated")]


class Aborts(BaseTestCase):
    def test(self):
        raise KeyboardInterrupt


class _Recorder(ReportModule):
    def __init__(self):
        super().__init__()
        self.events = []

    def on_event(self, event):
        self.events.append(event)


# --- order ---------------------------------------------------------------------


def test_stages_run_in_lifecycle_order_regardless_of_config_order():
    config = Config(
        entries=[
            step("dut_shutdown", PowerOff),
            tc(),
            step("dut_info", Collect),
            GeneratorEntry(name="gen", cls=cls_path(Gen)),
            FixtureEntry(name="dut", cls=cls_path(Dut), autoloaded=True),
            step("env_setup", Prepare),
            step("env_setup", Flash, image=Path("fw.bin")),
        ]
    )

    results = run_all(config)

    assert [r.verdict.status for r in results] == [VerdictStatus.PASSED, VerdictStatus.PASSED]
    assert CALLS == [
        "dut.setup",  # autoloaded, before everything else
        "generate",
        "env_setup",
        "dut.start",
        "flash:fw.bin:1",
        "dut.stop",
        "dut.lazy_stop",  # dut_info does not use the fixture
        "dut_info",
        "dut.start",
        "test",
        "dut.stop",
        "dut.start",
        "test",
        "dut.stop",
        "dut.lazy_stop",
        "dut_shutdown",
        "dut.teardown",
    ]


def test_steps_of_one_stage_run_in_config_order():
    config = Config(entries=[step("env_setup", Prepare, name="a"), step("env_setup", PowerOff, name="b")])
    run_all(config)
    assert CALLS == ["env_setup", "dut_shutdown"]


def test_steps_are_not_counted_as_tests():
    results = run_all(Config(entries=[step("env_setup", Prepare), step("dut_shutdown", PowerOff)]))
    assert results == []


# --- parameters ----------------------------------------------------------------


def test_step_params_are_mapped_onto_init_and_run(tmp_path):
    source = tmp_path / "config" / "env.yaml"
    flash = StepEntry(
        stage="env_setup",
        name="flash",
        cls=cls_path(Flash),
        params={"image": ConfigPath(path="resources/fw.bin", source=source), "retries": "3"},
        source=source,
    )
    config = Config(entries=[FixtureEntry(name="dut", cls=cls_path(Dut)), flash, tc()])

    results = run_all(config)

    assert results[0].verdict.status is VerdictStatus.PASSED
    assert "flash:fw.bin:3" in CALLS


def test_unknown_step_param_fails_the_setup():
    config = Config(entries=[step("env_setup", Prepare, typo=1), tc()])

    (result,) = run_all(config)

    assert result.verdict.status is VerdictStatus.SKIPPED
    assert "env_setup step 'Prepare' failed" in result.verdict.message
    assert "typo" in result.verdict.message
    assert CALLS == []


def test_missing_fixture_fails_the_setup():
    (result,) = run_all(Config(entries=[step("env_setup", Flash, image=Path("fw.bin")), tc()]))
    assert result.verdict.status is VerdictStatus.SKIPPED
    assert "'dut'" in result.verdict.message


# --- failures --------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["env_setup", "dut_info"])
def test_failed_setup_step_skips_remaining_setup_and_all_tests(stage):
    config = Config(
        entries=[
            step(stage, Fails),
            step("dut_info", Collect, name="later"),
            TestGroup(name="g", entries=[tc("a"), tc("b")]),
            step("dut_shutdown", PowerOff),
        ]
    )

    results = run_all(config)

    assert [r.verdict.status for r in results] == [VerdictStatus.SKIPPED, VerdictStatus.SKIPPED]
    assert results[0].verdict.message == f"{stage} step 'Fails' failed: RuntimeError: no power"
    assert CALLS == ["fails", "dut_shutdown"]


def test_generated_tests_are_skipped_after_a_failed_setup():
    config = Config(entries=[step("env_setup", Fails), GeneratorEntry(name="gen", cls=cls_path(Gen))])

    (result,) = run_all(config)

    assert result.name == "generated"
    assert result.verdict.status is VerdictStatus.SKIPPED


class BrokenGen(Generator):
    def generate(self):
        raise RuntimeError("bad sweep")


def test_broken_generator_stops_the_run_before_any_setup_step():
    config = Config(
        entries=[
            GeneratorEntry(name="gen", cls=cls_path(BrokenGen)),
            step("env_setup", Prepare),
            step("dut_shutdown", PowerOff),
        ]
    )

    with pytest.raises(ConfigError, match="bad sweep"):
        run_all(config)

    assert CALLS == ["dut_shutdown"]


@pytest.mark.parametrize(
    ("cls", "message"),
    [
        (ReturnsList, "run() returned list; expected a mapping or None"),
        (NotAStep, "is not a subclass of fixturerig.base.Step"),
    ],
)
def test_invalid_step_fails_the_setup(cls, message):
    (result,) = run_all(Config(entries=[step("dut_info", cls), tc()]))
    assert result.verdict.status is VerdictStatus.SKIPPED
    assert message in result.verdict.message
    assert "not_a_step" not in CALLS


def test_unknown_step_class_fails_the_setup():
    entry = StepEntry(stage="env_setup", name="missing", cls="no.such.module.Step")
    (result,) = run_all(Config(entries=[entry, tc()]))
    assert result.verdict.status is VerdictStatus.SKIPPED
    assert "no.such.module" in result.verdict.message


def test_every_shutdown_step_runs_even_if_one_fails():
    config = Config(
        entries=[step("dut_shutdown", Fails), step("dut_shutdown", PowerOff), tc()]
    )

    (result,) = run_all(config)

    assert result.verdict.status is VerdictStatus.PASSED
    assert CALLS == ["test", "fails", "dut_shutdown"]


def test_shutdown_runs_when_the_run_aborts():
    config = Config(
        entries=[
            FixtureEntry(name="dut", cls=cls_path(Dut), autoloaded=True),
            TestCaseEntry(name="a", cls=cls_path(Aborts)),
            step("dut_shutdown", PowerOff),
        ]
    )

    with pytest.raises(KeyboardInterrupt):
        run_all(config)

    assert CALLS[-2:] == ["dut_shutdown", "dut.teardown"]


# --- reporting -------------------------------------------------------------------


def _events(config: Config) -> list:
    recorder = _Recorder()
    run_all(config, ReportStream([recorder]))
    return recorder.events


def test_steps_are_reported_as_groups_with_their_content():
    config = Config(entries=[step("dut_info", Collect), tc(), step("dut_shutdown", PowerOff)])

    events = _events(config)

    assert [(e.kind, e.path) for e in events] == [
        ("run_started", ()),
        ("group_started", ("dut_info: Collect",)),
        ("text", ("dut_info: Collect",)),
        ("table", ("dut_info: Collect",)),
        ("group_finished", ("dut_info: Collect",)),
        ("test_started", ("t",)),
        ("test_finished", ("t",)),
        ("group_started", ("dut_shutdown: PowerOff",)),
        ("group_finished", ("dut_shutdown: PowerOff",)),
        ("run_finished", ()),
    ]
    table = events[3].table
    assert table.title == "Collect"
    assert table.headers == ["Name", "Value"]
    assert table.rows == [["serial", "SN-1"], ["version", 3], ["path", "fw.bin"]]
    assert events[-1].counts == {"passed": 1}


def test_failed_step_reports_an_error_verdict_in_its_group():
    events = _events(Config(entries=[step("env_setup", Fails)]))

    (verdict,) = [e for e in events if e.kind == "verdict"]
    assert verdict.path == ("env_setup: Fails",)
    assert verdict.test is None
    assert verdict.verdict.status is VerdictStatus.ERROR
    assert verdict.verdict.message == "RuntimeError: no power"


# --- phases ----------------------------------------------------------------------


def _full_config() -> Config:
    return Config(
        entries=[
            FixtureEntry(name="dut", cls=cls_path(Dut), autoloaded=True),
            step("env_setup", Prepare),
            step("env_setup", Flash, image=Path("fw.bin")),
            step("dut_info", Collect),
            tc(),
            step("dut_shutdown", PowerOff),
        ]
    )


def test_each_phase_runs_only_its_own_stage():
    with RunSession(_full_config()) as session:
        assert CALLS == ["dut.setup"]
        run_env_setup(session)
        assert CALLS[1:] == ["env_setup", "dut.start", "flash:fw.bin:1", "dut.stop"]
        run_dut_info(session)
        assert CALLS[-1] == "dut_info"
        del CALLS[:]
        results = run_tests(session)
        assert CALLS == ["dut.start", "test", "dut.stop"]
        run_dut_shutdown(session)
        assert CALLS[-1] == "dut_shutdown"
    assert CALLS[-1] == "dut.teardown"
    assert [r.name for r in results] == ["t"]
    assert session.results == results


def test_run_tests_requires_the_generators_to_have_run():
    config = Config(entries=[GeneratorEntry(name="gen", cls=cls_path(Gen))])
    with RunSession(config) as session:
        with pytest.raises(ConfigError, match="call run_generators"):
            run_tests(session)
        run_generators(session)
        (result,) = run_tests(session)
    assert result.name == "generated"


def test_failed_setup_phase_makes_later_setup_phases_no_ops():
    config = Config(entries=[step("env_setup", Fails), step("dut_info", Collect), tc()])
    with RunSession(config) as session:
        run_env_setup(session)
        run_dut_info(session)
        (result,) = run_tests(session)
    assert CALLS == ["fails"]
    assert session.setup_failure == "env_setup step 'Fails' failed: RuntimeError: no power"
    assert result.verdict.status is VerdictStatus.SKIPPED


def test_session_reports_run_boundaries_and_counts_across_run_tests_calls():
    recorder = _Recorder()
    with RunSession(Config(entries=[tc()]), ReportStream([recorder])) as session:
        run_tests(session)
        run_tests(session)
    kinds = [e.kind for e in recorder.events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    assert recorder.events[-1].counts == {"passed": 2}


class ReportingGen(Generator):
    def generate(self):
        report.text("generating")
        return []


def test_generators_report_into_the_session_stream():
    recorder = _Recorder()
    config = Config(entries=[GeneratorEntry(name="gen", cls=cls_path(ReportingGen))])
    with RunSession(config, ReportStream([recorder])) as session:
        run_generators(session)
    assert [e.kind for e in recorder.events] == ["run_started", "text", "run_finished"]


# --- interactive mode --------------------------------------------------------


def test_interactive_step_exception_ends_the_run_but_shutdown_still_runs():
    config = Config(
        entries=[
            step("env_setup", Fails),
            step("dut_shutdown", PowerOff),
            tc(),
        ]
    )

    with pytest.raises(RuntimeError, match="no power"):
        run_all(config, interactive=True)

    assert CALLS == ["fails", "dut_shutdown"]


def test_interactive_shutdown_step_exception_is_only_logged():
    config = Config(entries=[step("dut_shutdown", Fails), step("dut_shutdown", PowerOff), tc()])

    (result,) = run_all(config, interactive=True)

    assert result.verdict.status is VerdictStatus.PASSED
    assert CALLS == ["test", "fails", "dut_shutdown"]
