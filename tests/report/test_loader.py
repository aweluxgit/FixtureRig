from pathlib import Path

import pytest

from fixturerig.base import Fixture
from fixturerig.config.model import Config, ConfigError, Report, TestCase, TestGroup
from fixturerig.config.parse_yaml import parse_yaml_file, read_config_files
from fixturerig.report import ColoredConsoleReport, ConsoleReport, ReportModule
from fixturerig.report.json_report import JsonReport
from fixturerig.report.loader import build_report_stream, create_report_module


class NeedsFixture(ReportModule):
    def __init__(self, rig: Fixture, **kwargs):
        super().__init__(**kwargs)


class Explodes(ReportModule):
    def __init__(self, **kwargs):
        raise RuntimeError("no license")


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


# --- parsing -------------------------------------------------------------------


def test_parse_report_entry_and_traceability(tmp_path):
    path = _write(
        tmp_path,
        """
- report:
    class: fixturerig.report.json_report.JsonReport
    parametermap:
      path: out/results.json
- testgroup:
    name: Power
    entries:
      - report:
          name: html
          class: fixturerig.report.html.HtmlReport
      - testcase:
          name: ramp
          class: pkg.Ramp
          traceability: [REQ-1, 42]
      - testcase:
          name: single
          class: pkg.Single
          traceability: REQ-2
""",
    )
    config = parse_yaml_file(path)

    json_entry, html_entry = config.reports()
    assert json_entry == Report(
        cls="fixturerig.report.json_report.JsonReport",
        params={"path": "out/results.json"},
        source=path,
    )
    assert html_entry.name == "html"
    ramp, single = config.testcases()
    assert ramp.traceability == ["REQ-1", "42"]
    assert single.traceability == ["REQ-2"]


@pytest.mark.parametrize(
    "body, message",
    [
        ("- report:\n    name: x\n", "report 'x' has no 'class'"),
        ("- report:\n    class: a.B\n    pathx: 1\n", "unknown key"),
        ("- testcase:\n    name: t\n    class: a.B\n    traceability: {a: 1}\n", "traceability"),
    ],
)
def test_parse_rejects_invalid_report_and_traceability(tmp_path, body, message):
    with pytest.raises(ConfigError, match=message):
        read_config_files(Config(entries=[]), [_write(tmp_path, body)])


# --- module creation -------------------------------------------------------------


def test_create_maps_params_with_type_conversion(tmp_path):
    module = create_report_module(
        Report(cls="fixturerig.report.json_report.JsonReport", params={"path": str(tmp_path / "r.json"), "indent": "4"})
    )
    assert isinstance(module, JsonReport)
    assert module.path == tmp_path / "r.json"
    assert module.indent == 4


def test_create_passes_inherited_params_through_kwargs():
    module = create_report_module(
        Report(
            cls="fixturerig.report.console.ColoredConsoleReport",
            params={"force_color": True, "verbosity": 1, "exclude": ["chart"]},
        )
    )
    assert isinstance(module, ColoredConsoleReport)
    assert module.force_color is True
    assert module.verbosity == 1
    assert module.exclude == {"chart"}


@pytest.mark.parametrize(
    "entry, message",
    [
        (Report(cls="nowhere.Report"), "Could not import"),
        (Report(cls="fixturerig.config.model.Config"), "not a subclass"),
        (Report(cls="fixturerig.report.json_report.JsonReport", params={"pth": "x"}), "Unknown parameter"),
        (Report(cls=f"{__name__}.NeedsFixture", params={"rig": "psu"}), "fixture reference"),
        (Report(cls="fixturerig.report.console.ConsoleReport", params={"verbosity": 7}), "verbosity"),
        (Report(cls=f"{__name__}.Explodes"), "no license"),
        (Report(cls="fixturerig.report.console.ConsoleReport", params={"exclude": ["nope"]}), "Unknown event kind"),
    ],
)
def test_create_reports_problems_as_config_errors(entry, message):
    with pytest.raises(ConfigError, match=message):
        create_report_module(entry)


def test_config_error_names_source_file():
    entry = Report(cls="nowhere.Report", name="ci", source=Path("rig.yaml"))
    with pytest.raises(ConfigError, match=r"rig.yaml: report 'ci'"):
        create_report_module(entry)


# --- default console ---------------------------------------------------------------


def test_console_report_is_active_by_default(tmp_path):
    config = Config(
        entries=[Report(cls="fixturerig.report.json_report.JsonReport", params={"path": str(tmp_path / "r.json")})]
    )
    modules = build_report_stream(config).modules
    assert [type(m) for m in modules] == [ConsoleReport, JsonReport]


def test_configured_console_replaces_the_default():
    config = Config(
        entries=[
            TestGroup(entries=[Report(cls="fixturerig.report.console.ColoredConsoleReport")]),
            TestCase(name="t", cls="pkg.T"),
        ]
    )
    modules = build_report_stream(config).modules
    assert [type(m) for m in modules] == [ColoredConsoleReport]
