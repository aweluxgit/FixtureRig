import sys
from pathlib import Path

import pytest

from fixturerig.config.model import Config, ConfigError, ConfigPath, PythonPath, TestGroup
from fixturerig.core.class_loader import add_python_paths, load_class


@pytest.fixture(autouse=True)
def _isolated_sys_path(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in [n for n in sys.modules if n.split(".")[0] in {"rig_project", "rig_extra"}]:
        del sys.modules[name]


def _entry(path: str, source: Path, **bases) -> PythonPath:
    return PythonPath(path=ConfigPath(path, source=source, **bases), source=source)


def _package(directory: Path, name: str, body: str = "") -> None:
    package = directory / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(body, encoding="utf-8")


def test_adds_directories_in_config_order_before_existing_entries(tmp_path):
    source = tmp_path / "config" / "rig.yaml"
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    before = list(sys.path)
    config = Config(entries=[_entry("../a", source), TestGroup(entries=[_entry("../b", source)])])

    added = add_python_paths(config)

    assert added == [tmp_path / "a", tmp_path / "b"]
    assert sys.path == [str(tmp_path / "a"), str(tmp_path / "b"), *before]


def test_configured_classes_become_loadable(tmp_path):
    _package(tmp_path / "project", "rig_project", "class Psu:\n    pass\n")
    config = Config(entries=[_entry("project", tmp_path / "rig.yaml")])

    add_python_paths(config)

    assert load_class("rig_project.Psu").__name__ == "Psu"


def test_entries_already_on_sys_path_are_skipped(tmp_path):
    sys.path.insert(0, str(tmp_path))
    config = Config(entries=[_entry(".", tmp_path / "rig.yaml")])
    assert add_python_paths(config) == []
    assert sys.path.count(str(tmp_path)) == 1


def test_later_entry_may_use_base_module_from_earlier_entry(tmp_path):
    _package(tmp_path / "project", "rig_project")
    (tmp_path / "project" / "rig_project" / "plugins").mkdir()
    source = tmp_path / "rig.yaml"
    config = Config(
        entries=[_entry("project", source), _entry("plugins", source, base_module="rig_project")]
    )

    added = add_python_paths(config)

    assert added[1] == tmp_path / "project" / "rig_project" / "plugins"


@pytest.mark.parametrize(
    "path, message",
    [
        ("missing", "which is not a directory"),
        ("file.txt", "which is not a directory"),
        ("https://rig.example/lib", "is a URI"),
    ],
)
def test_invalid_pythonpath_is_a_config_error(tmp_path, path, message):
    (tmp_path / "file.txt").write_text("x")
    config = Config(entries=[_entry(path, tmp_path / "rig.yaml")])
    with pytest.raises(ConfigError, match=message):
        add_python_paths(config)


def test_unknown_base_module_is_a_config_error(tmp_path):
    config = Config(entries=[_entry("x", tmp_path / "rig.yaml", base_module="no_such_package")])
    with pytest.raises(ConfigError, match="cannot be found"):
        add_python_paths(config)
