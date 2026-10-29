from pathlib import Path

import pytest

from fixturerig.config.model import Config, ConfigError, ConfigPath, Fixture, Generator, Step, TestCase, TestGroup
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


def test_missing_class_is_rejected_after_merging(tmp_path):
    path = _write(tmp_path, "config.yaml", "- fixture:\n    name: can\n")

    assert parse_yaml_file(path).entries[0].cls is None
    with pytest.raises(ConfigError, match="fixture 'can' has no 'class'"):
        read_config_files(Config(entries=[]), [path])


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
    assert second.autoloaded is None  # not configured: not autoloaded


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
    with pytest.raises(ConfigError, match="unnamed generator has no 'name'"):
        read_config_files(Config(entries=[]), [path])


def test_generator_create_group_must_be_a_bool(tmp_path):
    path = _write(tmp_path, "config.yaml", "- generator:\n    name: g\n    class: pkg.G\n    create_group: maybe\n")
    with pytest.raises(ConfigError, match="create_group must be true or false"):
        parse_yaml_file(path)


def test_parses_lifecycle_steps(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        """
        - env_setup:
            name: prepare
            class: project.setup.Prepare
        - env_setup:
            name: flash
            class: project.setup.Flash
            parameterpath:
              path: resources/firmware.bin
        - dut_info:
            name: collect
            class: project.info.Collect
            parametermap:
              verbose: true
        - dut_shutdown:
            name: power_off
            class: project.setup.PowerOff
        """,
    )

    config = parse_yaml_file(path)

    assert config.entries == [
        Step(stage="env_setup", name="prepare", cls="project.setup.Prepare", source=path),
        Step(
            stage="env_setup",
            name="flash",
            cls="project.setup.Flash",
            params={"path": ConfigPath(path="resources/firmware.bin", source=path)},
            source=path,
        ),
        Step(stage="dut_info", name="collect", cls="project.info.Collect", params={"verbose": True}, source=path),
        Step(stage="dut_shutdown", name="power_off", cls="project.setup.PowerOff", source=path),
    ]


@pytest.mark.parametrize("stage", ["env_setup", "dut_info", "dut_shutdown"])
def test_step_requires_name_and_class(tmp_path, stage):
    path = _write(tmp_path, "config.yaml", f"- {stage}:\n    class: pkg.S\n")
    with pytest.raises(ConfigError, match=f"unnamed {stage} has no 'name'"):
        read_config_files(Config(entries=[]), [path])
    path = _write(tmp_path, "config.yaml", f"- {stage}:\n    name: s\n")
    with pytest.raises(ConfigError, match=f"{stage} 's' has no 'class'"):
        read_config_files(Config(entries=[]), [path])


def test_step_rejects_unknown_keys(tmp_path):
    path = _write(tmp_path, "config.yaml", "- env_setup:\n    name: s\n    class: pkg.S\n    autoloaded: true\n")
    with pytest.raises(ConfigError, match="unknown key"):
        parse_yaml_file(path)


def test_step_inside_testgroup_rejected(tmp_path):
    path = _write(
        tmp_path,
        "config.yaml",
        "- testgroup:\n    name: g\n    entries:\n    - env_setup:\n        name: s\n        class: pkg.S\n",
    )
    with pytest.raises(ConfigError, match="not allowed inside a testgroup"):
        parse_yaml_file(path)


def test_unknown_entry_kind_lists_stages(tmp_path):
    path = _write(tmp_path, "config.yaml", "- dut_teardown:\n    name: s\n    class: pkg.S\n")
    with pytest.raises(ConfigError, match="'dut_shutdown'"):
        parse_yaml_file(path)


def test_dut_setup_is_not_an_entry_kind(tmp_path):
    path = _write(tmp_path, "config.yaml", "- dut_setup:\n    name: s\n    class: pkg.S\n")
    with pytest.raises(ConfigError, match="unknown config entry kind 'dut_setup'"):
        parse_yaml_file(path)


def test_option_only_entries_need_no_class(tmp_path):
    path = _write(
        tmp_path,
        "options.yaml",
        """
        - testcase:
            name: t
            option_only: true
            parametermap:
              limit: 5.0
        - generator:
            name: gen
            option_only: true
        - testgroup:
            name: g
            option_only: true
        """,
    )

    testcase, generator, group = parse_yaml_file(path).entries

    assert testcase == TestCase(name="t", cls=None, params={"limit": 5.0}, source=path, option_only=True)
    assert generator.option_only and generator.cls is None and generator.create_group is None
    assert group.option_only


def test_active_entries_still_require_a_class(tmp_path):
    path = _write(tmp_path, "c.yaml", "- testcase:\n    name: t\n    option_only: false\n")
    with pytest.raises(ConfigError, match="testcase 't' has no 'class'"):
        read_config_files(Config(entries=[]), [path])


def test_option_only_entries_are_not_validated(tmp_path):
    path = _write(tmp_path, "c.yaml", "- testcase:\n    name: t\n    option_only: true\n")
    config = read_config_files(Config(entries=[]), [path])
    assert config.testcases() == []


def test_regular_entries_merge_across_files(tmp_path):
    tests = _write(
        tmp_path,
        "test.yaml",
        """
        - fixture: {name: psu, class: pkg.Psu, parametermap: {port: COM1}}
        - testgroup:
            name: g
            entries:
              - testcase: {name: t, class: pkg.T, parametermap: {a: 1}}
        - env_setup: {name: flash, class: pkg.Flash}
        - dut_info: {name: flash, class: pkg.Info}
        """,
    )
    more = _write(
        tmp_path,
        "test2.yaml",
        """
        - testgroup:
            name: g
            entries:
              - testcase: {name: t, parametermap: {b: 2}}
        - fixture: {name: psu, autoloaded: true, parametermap: {port: COM2}}
        - env_setup: {name: flash, parametermap: {image: fw.bin}}
        """,
    )

    config = read_config_files(Config(entries=[]), [tests, more])

    (psu,) = config.fixtures()
    assert (psu.cls, psu.params, psu.autoloaded, psu.source) == ("pkg.Psu", {"port": "COM2"}, True, tests)
    (testcase,) = config.testcases()
    assert (testcase.cls, testcase.params) == ("pkg.T", {"a": 1, "b": 2})
    assert [(s.stage, s.cls, s.params) for s in config.steps()] == [
        ("env_setup", "pkg.Flash", {"image": "fw.bin"}),
        ("dut_info", "pkg.Info", {}),
    ]


def test_entry_can_be_completed_later_in_the_same_file(tmp_path):
    path = _write(
        tmp_path,
        "c.yaml",
        """
        - testcase: {name: t, parametermap: {a: 1}}
        - testcase: {name: t, class: pkg.T}
        """,
    )
    (testcase,) = read_config_files(Config(entries=[]), [path]).testcases()
    assert (testcase.cls, testcase.params) == ("pkg.T", {"a": 1})


def test_option_only_must_be_a_bool(tmp_path):
    path = _write(tmp_path, "c.yaml", "- testcase:\n    name: t\n    option_only: yes please\n")
    with pytest.raises(ConfigError, match="option_only must be true or false"):
        parse_yaml_file(path)


def test_option_only_group_makes_nested_entries_option_only(tmp_path):
    path = _write(
        tmp_path,
        "options.yaml",
        """
        - testgroup:
            name: g
            option_only: true
            entries:
              - testcase: {name: t}
              - testgroup:
                  - generator: {name: gen}
        """,
    )

    (group,) = parse_yaml_file(path).entries
    testcase, anonymous = group.entries

    assert testcase.option_only
    assert anonymous.option_only
    assert anonymous.entries[0].option_only


def test_option_only_false_inside_option_only_group_rejected(tmp_path):
    path = _write(
        tmp_path,
        "c.yaml",
        """
        - testgroup:
            name: g
            option_only: true
            entries:
              - testcase: {name: t, class: pkg.T, option_only: false}
        """,
    )
    with pytest.raises(ConfigError, match="can't set option_only to false"):
        parse_yaml_file(path)


@pytest.mark.parametrize(
    "entry",
    [
        "fixture: {name: f, class: pkg.F}",
        "report: {class: pkg.R}",
        "pythonpath: ..",
        "env_setup: {name: s, class: pkg.S}",
    ],
)
def test_option_only_group_rejects_other_entry_kinds(tmp_path, entry):
    path = _write(
        tmp_path,
        "c.yaml",
        f"- testgroup:\n    name: g\n    option_only: true\n    entries:\n      - {entry}\n",
    )
    with pytest.raises(ConfigError, match="not allowed inside an option_only testgroup"):
        parse_yaml_file(path)


def test_option_only_not_allowed_on_fixtures(tmp_path):
    path = _write(tmp_path, "c.yaml", "- fixture:\n    name: f\n    class: pkg.F\n    option_only: true\n")
    with pytest.raises(ConfigError, match="unknown key"):
        parse_yaml_file(path)


def test_read_config_files_merges_option_only_entries(tmp_path):
    options = _write(
        tmp_path,
        "options.yaml",
        """
        - testgroup:
            name: regression
            option_only: true
            entries:
              - testcase:
                  name: t1
                  traceability: REQ-9
                  parametermap: {limit: 5.0}
        """,
    )
    tests = _write(
        tmp_path,
        "test.yaml",
        """
        - testcase: {name: first, class: pkg.First}
        - testgroup:
            name: regression
            entries:
              - testcase: {name: t1, class: pkg.T1, parametermap: {limit: 4.5, value: 1}}
              - testcase: {name: t2, class: pkg.T2}
        """,
    )

    config = read_config_files(Config(entries=[]), [options, tests])

    assert [entry.name for entry in config.walk()] == ["first", "regression", "t1", "t2"]
    t1 = config.testcases()[1]
    assert t1.cls == "pkg.T1"
    assert t1.params == {"limit": 5.0, "value": 1}
    assert t1.traceability == ["REQ-9"]
    assert t1.source == tests
