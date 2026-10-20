from pathlib import Path

import pytest

import fixturerig
from fixturerig.config.model import ConfigError, ConfigPath
from fixturerig.config.parse_yaml import parse_yaml_file
from fixturerig.core.inheritance import ArgumentMappingError, map_config_to_method_args
from fixturerig.report.loader import create_report_module

PACKAGE_DIR = Path(fixturerig.__file__).parent


def _write(tmp_path: Path, text: str, name: str = "config/rig.yaml") -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- parsing -------------------------------------------------------------------


def test_parameterpath_string_is_shorthand_for_path(tmp_path):
    source = _write(
        tmp_path,
        """
- fixture:
    name: psu
    class: pkg.Psu
    parametermap:
      port: COM4
    parameterpath:
      calibration: cal/psu.yaml
      firmware: {path: fw.bin, base_module: fixturerig.report}
      log_dir: {path: logs, base_path: ../out}
""",
    )
    (fixture,) = parse_yaml_file(source).fixtures()

    assert fixture.params == {
        "port": "COM4",
        "calibration": ConfigPath("cal/psu.yaml", source=source),
        "firmware": ConfigPath("fw.bin", base_module="fixturerig.report", source=source),
        "log_dir": ConfigPath("logs", base_path="../out", source=source),
    }


def test_parameterpath_is_accepted_on_testcases_and_reports(tmp_path):
    source = _write(
        tmp_path,
        """
- testcase:
    name: t
    class: pkg.T
    parameterpath: {data: data.csv}
- report:
    class: pkg.R
    parameterpath: {path: out.json}
""",
    )
    config = parse_yaml_file(source)
    assert config.testcases()[0].params == {"data": ConfigPath("data.csv", source=source)}
    assert config.reports()[0].params == {"path": ConfigPath("out.json", source=source)}


@pytest.mark.parametrize(
    "section, message",
    [
        ("parameterpath: [a.txt]", "parameterpath must be a mapping"),
        ("parameterpath: {p: 3}", "must be a string or a mapping"),
        ("parameterpath: {p: {base_path: x}}", "missing required key 'path'"),
        ("parameterpath: {p: {path: a, relto: x}}", r"unknown key\(s\) \['relto'\]"),
        ("parameterpath: {p: {path: a, base_path: x, base_module: y}}", "mutually exclusive"),
        ("parameterpath: {p: ''}", "non-empty string"),
        ("parameterpath: {p: {path: a, base_path: 5}}", "'base_path' must be a non-empty string"),
        ("parametermap: {p: 1}\n    parameterpath: {p: a}", r"\['p'\] given in both"),
    ],
)
def test_invalid_parameterpath_is_a_config_error(tmp_path, section, message):
    source = _write(tmp_path, f"- fixture:\n    name: f\n    class: pkg.F\n    {section}\n")
    with pytest.raises(ConfigError, match=message):
        parse_yaml_file(source)


def test_config_error_names_file_and_parameter(tmp_path):
    source = _write(tmp_path, "- fixture:\n    name: f\n    class: pkg.F\n    parameterpath: {cal: 3}\n")
    with pytest.raises(ConfigError, match=r"rig.yaml: fixture parameterpath 'cal'"):
        parse_yaml_file(source)


# --- resolution ----------------------------------------------------------------


def test_relative_path_is_relative_to_the_config_file(tmp_path):
    source = tmp_path / "config" / "rig.yaml"
    assert ConfigPath("../reports/out.json", source=source).resolve() == tmp_path / "reports" / "out.json"


def test_relative_path_without_source_is_relative_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ConfigPath("a/./b/../c.txt").resolve() == tmp_path / "a" / "c.txt"


def test_base_path_relative_to_config_file(tmp_path):
    source = tmp_path / "config" / "rig.yaml"
    resolved = ConfigPath("logs", base_path="../out", source=source).resolve()
    assert resolved == tmp_path / "out" / "logs"


def test_absolute_base_path(tmp_path):
    resolved = ConfigPath("logs", base_path=str(tmp_path / "abs"), source=Path("/elsewhere/rig.yaml")).resolve()
    assert resolved == tmp_path / "abs" / "logs"


def test_base_module_package_uses_package_directory():
    resolved = ConfigPath("html.py", base_module="fixturerig.report").resolve()
    assert resolved == PACKAGE_DIR / "report" / "html.py"


def test_base_module_plain_module_uses_its_directory():
    resolved = ConfigPath("html.py", base_module="fixturerig.report.pdf").resolve()
    assert resolved == PACKAGE_DIR / "report" / "html.py"


@pytest.mark.parametrize("module", ["no_such_package.mod", "fixturerig.no_such_module"])
def test_unknown_base_module_is_a_config_error(module):
    with pytest.raises(ConfigError, match="cannot be found"):
        ConfigPath("x", base_module=module).resolve()


def test_absolute_path_ignores_base(tmp_path):
    absolute = tmp_path / "fixed.bin"
    assert ConfigPath(str(absolute), base_module="fixturerig.report").resolve() == absolute
    assert ConfigPath(str(absolute), base_path="other", source=Path("x/rig.yaml")).resolve() == absolute


def test_file_uri_resolves_to_local_path(tmp_path):
    uri = (tmp_path / "with space.txt").as_uri()
    assert ConfigPath(uri, base_path="ignored").resolve() == tmp_path / "with space.txt"


def test_other_uris_are_passed_through():
    path = ConfigPath("https://rig.example/cal/psu.yaml", source=Path("config/rig.yaml"))
    assert path.is_uri
    assert path.resolve() == "https://rig.example/cal/psu.yaml"


def test_windows_drive_is_not_a_uri():
    assert not ConfigPath("C:/data/cal.yaml").is_uri


# --- conversion through argument mapping ------------------------------------------------


class Target:
    def __init__(self, path: Path, text: str = "", any_value=None, url: str = ""):
        self.path = path
        self.text = text
        self.any_value = any_value
        self.url = url


def test_param_paths_are_resolved_and_converted_by_type_hint(tmp_path):
    source = tmp_path / "config" / "rig.yaml"
    kwargs = map_config_to_method_args(
        {
            "path": ConfigPath("out/a.json", source=source),
            "text": ConfigPath("b.txt", source=source),
            "any_value": ConfigPath("c.txt", source=source),
            "url": ConfigPath("https://rig.example/x", source=source),
        },
        Target,
    )
    assert kwargs == {
        "path": tmp_path / "config" / "out" / "a.json",
        "text": str(tmp_path / "config" / "b.txt"),
        "any_value": tmp_path / "config" / "c.txt",
        "url": "https://rig.example/x",
    }


def test_uri_for_a_path_parameter_is_an_error():
    with pytest.raises(ArgumentMappingError, match="is a URI, not a local path"):
        map_config_to_method_args({"path": ConfigPath("https://rig.example/x")}, Target)


def test_plain_uri_string_for_a_path_parameter_is_an_error():
    with pytest.raises(ArgumentMappingError, match="is a URI"):
        map_config_to_method_args({"path": "https://rig.example/x"}, Target)


def test_unknown_base_module_is_an_argument_mapping_error():
    with pytest.raises(ArgumentMappingError, match="cannot be found"):
        map_config_to_method_args({"path": ConfigPath("x", base_module="no_such_package")}, Target)


def test_report_output_path_is_relative_to_its_config_file(tmp_path):
    source = _write(
        tmp_path,
        """
- report:
    class: fixturerig.report.json_report.JsonReport
    parameterpath:
      path: ../reports/report.json
""",
    )
    module = create_report_module(parse_yaml_file(source).reports()[0])
    assert module.path == tmp_path / "reports" / "report.json"


# --- pythonpath entries share the path value syntax ---------------------------------


def test_pythonpath_entries_are_anonymous_config_paths(tmp_path):
    source = _write(
        tmp_path,
        """
- pythonpath: ..
- pythonpath: {path: lib, base_module: fixturerig.report}
- testgroup:
  - pythonpath: {path: vendor, base_path: ../third_party}
""",
    )
    config = parse_yaml_file(source)

    assert [entry.path for entry in config.python_paths()] == [
        ConfigPath("..", source=source),
        ConfigPath("lib", base_module="fixturerig.report", source=source),
        ConfigPath("vendor", base_path="../third_party", source=source),
    ]
    assert config.python_paths()[0].path.resolve() == tmp_path


@pytest.mark.parametrize(
    "value, message",
    [
        ("[a, b]", "pythonpath must be a string or a mapping"),
        ("{base_path: x}", "pythonpath: missing required key 'path'"),
        ("{path: a, name: x}", r"pythonpath: unknown key\(s\) \['name'\]"),
        ("{path: a, base_path: x, base_module: y}", "pythonpath: .*mutually exclusive"),
    ],
)
def test_invalid_pythonpath_is_a_config_error(tmp_path, value, message):
    with pytest.raises(ConfigError, match=message):
        parse_yaml_file(_write(tmp_path, f"- pythonpath: {value}\n"))
