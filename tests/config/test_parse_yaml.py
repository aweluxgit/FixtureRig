from pathlib import Path

import pytest

from fixturerig.config.model import ConfigError, Fixture, TestCase, TestGroup
from fixturerig.config.parse_yaml import read_configs, parse_yaml_file


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_parses_fixture_and_testcase(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        """
        - fixture:
            name: can
            class: fixturerig.fixtures.can.Can
            parametermap:
              port: COM4
        - testcase:
            name: voltage_limit
            class: project.tests.VoltageLimitTest
            parametermap:
              limit: 4.5
        """,
    )

    config = parse_yaml_file(path)

    assert config.entries == [
        Fixture(name="can", cls="fixturerig.fixtures.can.Can", params={"port": "COM4"}, source=path),
        TestCase(
            name="voltage_limit",
            cls="project.tests.VoltageLimitTest",
            params={"limit": 4.5},
            source=path,
        ),
    ]


def test_fixture_without_parametermap_gets_empty_params(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        """
        - fixture:
            name: can
            class: fixturerig.fixtures.can.Can
        """,
    )

    config = parse_yaml_file(path)

    assert config.entries == [Fixture(name="can", cls="fixturerig.fixtures.can.Can", params={}, source=path)]


def test_anonymous_testgroup_list_form(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        """
        - testgroup:
          - testcase:
              name: foo
              class: project.tests.Foo
        """,
    )

    config = parse_yaml_file(path)

    assert len(config.entries) == 1
    group = config.entries[0]
    assert isinstance(group, TestGroup)
    assert group.name is None
    assert group.entries == [TestCase(name="foo", cls="project.tests.Foo", params={}, source=path)]


def test_named_testgroup_map_form(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        """
        - testgroup:
            name: my_group
            entries:
              - testcase:
                  name: foo
                  class: project.tests.Foo
        """,
    )

    config = parse_yaml_file(path)

    group = config.entries[0]
    assert isinstance(group, TestGroup)
    assert group.name == "my_group"
    assert len(group.entries) == 1


def test_empty_document_yields_no_entries(tmp_path):
    path = _write(tmp_path, "config.yaml", "")

    config = parse_yaml_file(path)

    assert config.entries == []


def test_top_level_must_be_a_list(tmp_path):
    path = _write(tmp_path, "config.yaml", "fixture:\n  name: can\n  class: pkg.Can\n")

    with pytest.raises(ConfigError, match="must be a list"):
        parse_yaml_file(path)


def test_unknown_entry_kind_rejected(tmp_path):
    path = _write(tmp_path, "config.yaml", "- widget:\n    name: x\n")

    with pytest.raises(ConfigError, match="unknown config entry kind"):
        parse_yaml_file(path)


def test_entry_with_multiple_keys_rejected(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        "- fixture:\n    name: can\n    class: pkg.Can\n  testcase:\n    name: x\n    class: pkg.X\n",
    )

    with pytest.raises(ConfigError, match="single-key mapping"):
        parse_yaml_file(path)


def test_unknown_key_in_fixture_rejected(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        "- fixture:\n    name: can\n    class: pkg.Can\n    typo: 1\n",
    )

    with pytest.raises(ConfigError, match="unknown key"):
        parse_yaml_file(path)


def test_missing_required_key_rejected(tmp_path):
    path = _write(tmp_path, "config.yaml", "- fixture:\n    name: can\n")

    with pytest.raises(ConfigError, match="missing required key"):
        parse_yaml_file(path)


def test_parametermap_must_be_a_mapping(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        "- fixture:\n    name: can\n    class: pkg.Can\n    parametermap: [1, 2]\n",
    )

    with pytest.raises(ConfigError, match="parametermap must be a mapping"):
        parse_yaml_file(path)


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match="Could not read"):
        parse_yaml_file(tmp_path / "does_not_exist.yaml")


def test_load_config_merges_files_in_order(tmp_path):
    first = _write(tmp_path, "first.yaml", "- fixture:\n    name: a\n    class: pkg.A\n")
    second = _write(tmp_path, "second.yaml", "- fixture:\n    name: b\n    class: pkg.B\n")

    config = read_configs([first, second])

    assert [entry.name for entry in config.entries] == ["a", "b"]
