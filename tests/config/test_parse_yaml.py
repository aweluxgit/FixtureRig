from pathlib import Path

import pytest

from fixturerig.config.model import Config, ConfigError, Fixture, Generator, TestCase, TestGroup
from fixturerig.config.parse_yaml import parse_yaml_file, read_config_files


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

    config = read_config_files(Config(entries=[]), [first, second])

    assert [entry.name for entry in config.entries] == ["a", "b"]


def test_testcase_fixturemap(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        """
        - testcase:
            name: t
            class: pkg.Test
            fixturemap:
              power_supply: psu_bench_2
            parametermap:
              limit: 4.5
        """,
    )

    (entry,) = parse_yaml_file(path).entries

    assert entry.fixturemap == {"power_supply": "psu_bench_2"}
    assert entry.params == {"limit": 4.5}


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("    fixturemap: [psu]\n", "fixturemap must be a mapping"),
        ("    fixturemap: {psu: 3}\n", "must map parameter names to fixture names"),
        ("    fixturemap: {psu: a}\n    parametermap: {psu: b}\n", "both fixturemap and parametermap"),
    ],
)
def test_invalid_fixturemap_rejected(tmp_path, body, message):
    path = _write(tmp_path, "config.yaml", "- testcase:\n    name: t\n    class: pkg.Test\n" + body)

    with pytest.raises(ConfigError, match=message):
        parse_yaml_file(path)


def test_fixturemap_only_allowed_on_testcases(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        "- fixture:\n    name: can\n    class: pkg.Can\n    fixturemap: {a: b}\n",
    )

    with pytest.raises(ConfigError, match="unknown key"):
        parse_yaml_file(path)


def test_fixture_autoloaded(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        "- fixture:\n    name: a\n    class: pkg.A\n    autoloaded: true\n"
        "- fixture:\n    name: b\n    class: pkg.B\n",
    )

    first, second = parse_yaml_file(path).entries

    assert first.autoloaded is True
    assert second.autoloaded is False


def test_fixture_autoloaded_must_be_a_boolean(tmp_path):
    path = _write(tmp_path, "config.yaml", "- fixture:\n    name: a\n    class: pkg.A\n    autoloaded: yes please\n")

    with pytest.raises(ConfigError, match="autoloaded must be true or false"):
        parse_yaml_file(path)


def test_parses_generator(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        """
        - generator:
            name: sweep
            class: project.generators.Sweep
            parametermap:
              values: [1, 2]
        - generator:
            name: other
            class: project.generators.Other
            create_group: false
        """,
    )

    config = parse_yaml_file(path)

    assert config.entries == [
        Generator(name="sweep", cls="project.generators.Sweep", params={"values": [1, 2]}, source=path),
        Generator(name="other", cls="project.generators.Other", source=path, create_group=False),
    ]


def test_generator_rejects_unknown_keys(tmp_path):
    path = _write(tmp_path, "config.yaml", "- generator:\n    name: g\n    class: pkg.G\n    entries: []\n")
    with pytest.raises(ConfigError, match="unknown key"):
        parse_yaml_file(path)


def test_generator_requires_a_name(tmp_path):
    path = _write(tmp_path, "config.yaml", "- generator:\n    class: pkg.G\n")
    with pytest.raises(ConfigError, match="missing required key"):
        parse_yaml_file(path)


def test_generator_create_group_must_be_a_bool(tmp_path):
    path = _write(tmp_path, "config.yaml", "- generator:\n    name: g\n    class: pkg.G\n    create_group: maybe\n")
    with pytest.raises(ConfigError, match="create_group must be true or false"):
        parse_yaml_file(path)
