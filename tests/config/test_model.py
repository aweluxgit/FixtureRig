from pathlib import Path

import pytest

from fixturerig.config.model import (
    Config,
    ConfigError,
    ConfigPath,
    Fixture,
    Generator,
    PythonPath,
    Report,
    Step,
    TestCase,
    TestGroup,
)


def test_extend_appends_entries_in_order():
    first = Config(entries=[Fixture(name="a", cls="pkg.A")])
    second = Config(entries=[Fixture(name="b", cls="pkg.B")])

    first.extend(second)

    assert [entry.name for entry in first.entries] == ["a", "b"]


def test_walk_recurses_into_groups():
    inner = TestCase(name="inner", cls="pkg.Inner")
    group = TestGroup(entries=[inner], name="group")
    outer = Fixture(name="outer", cls="pkg.Outer")
    config = Config(entries=[outer, group])

    assert list(config.walk()) == [outer, group, inner]


def test_fixtures_and_testcases_include_nested_entries():
    nested_fixture = Fixture(name="nested-fixture", cls="pkg.NestedFixture")
    nested_testcase = TestCase(name="nested-testcase", cls="pkg.NestedTestCase")
    group = TestGroup(entries=[nested_fixture, nested_testcase])
    top_fixture = Fixture(name="top-fixture", cls="pkg.TopFixture")
    config = Config(entries=[top_fixture, group])

    assert config.fixtures() == [top_fixture, nested_fixture]
    assert config.testcases() == [nested_testcase]


def test_entries_carry_source_path():
    source = Path("some/config.yaml")
    fixture = Fixture(name="a", cls="pkg.A", source=source)

    assert fixture.source == source


def test_steps_filters_by_stage_in_config_order():
    flash = Step(stage="env_setup", name="flash", cls="pkg.Flash")
    collect = Step(stage="dut_info", name="collect", cls="pkg.Collect")
    power = Step(stage="env_setup", name="power", cls="pkg.Power")
    config = Config(entries=[flash, Fixture(name="a", cls="pkg.A"), collect, power])

    assert config.steps() == [flash, collect, power]
    assert config.steps("env_setup") == [flash, power]
    assert config.steps("dut_shutdown") == []


def test_step_rejects_unknown_stage():
    with pytest.raises(ConfigError, match="Unknown stage"):
        Step(stage="dut_teardown", name="x", cls="pkg.X")
    with pytest.raises(ConfigError, match="Unknown stage"):
        Step(stage="dut_setup", name="x", cls="pkg.X")
    with pytest.raises(ConfigError, match="Unknown stage"):
        Config().steps("dut_teardown")


# --- option_only merge -------------------------------------------------------


def _merged(*configs: Config) -> Config:
    merged = Config(entries=[])
    for config in configs:
        merged.extend(config)
    return merged


def test_option_only_entries_are_skipped_by_walk():
    nested = TestCase(name="nested", cls="pkg.Nested")
    option_group = TestGroup(name="g", entries=[nested], option_only=True)
    option_case = TestCase(name="t", cls="pkg.T", option_only=True)
    option_generator = Generator(name="gen", cls="pkg.Gen", option_only=True)
    config = Config(entries=[option_group, option_case, option_generator])

    assert list(config.walk()) == []
    assert config.testcases() == []
    assert config.generators() == []


def test_new_option_only_entry_is_added_inactive():
    config = _merged(Config(entries=[TestCase(name="t", cls=None, params={"a": 1}, option_only=True)]))

    assert len(config.entries) == 1
    assert config.testcases() == []


def test_option_only_entry_merges_into_earlier_entry():
    regular = TestCase(name="t", cls="pkg.T", params={"a": 1, "b": 2}, source=Path("test.yaml"))
    other = TestCase(name="other", cls="pkg.Other")
    option = TestCase(name="t", cls=None, params={"b": 3, "c": 4}, source=Path("options.yaml"), option_only=True)

    config = _merged(Config(entries=[regular, other]), Config(entries=[option]))

    assert config.entries == [regular, other]
    assert regular.cls == "pkg.T"
    assert regular.params == {"a": 1, "b": 3, "c": 4}
    assert regular.source == Path("test.yaml")
    assert not regular.option_only


def test_earlier_option_only_entry_moves_to_the_regular_entry():
    option = TestCase(name="t", cls=None, params={"b": 3}, traceability=["REQ-2"], option_only=True)
    other = TestCase(name="other", cls="pkg.Other")
    regular = TestCase(name="t", cls="pkg.T", params={"a": 1, "b": 2}, traceability=["REQ-1"])

    config = _merged(Config(entries=[option]), Config(entries=[other, regular]))

    assert config.entries == [other, regular]
    assert config.testcases() == [other, regular]
    assert regular.params == {"a": 1, "b": 3}
    assert regular.traceability == ["REQ-1", "REQ-2"]
    assert not regular.option_only


def test_two_option_only_entries_merge_and_stay_inactive():
    first = TestCase(name="t", cls=None, params={"a": 1, "b": 1}, option_only=True)
    second = TestCase(name="t", cls="pkg.T", params={"b": 2}, option_only=True)

    config = _merged(Config(entries=[first]), Config(entries=[second]))

    assert config.entries == [first]
    assert first.option_only
    assert first.cls == "pkg.T"
    assert first.params == {"a": 1, "b": 2}
    assert config.testcases() == []


def test_regular_entries_merge_with_later_values_winning():
    first = TestCase(name="t", cls="pkg.T", params={"a": 1, "b": 1}, source=Path("test.yaml"))
    other = TestCase(name="other", cls="pkg.Other")
    second = TestCase(name="t", cls=None, params={"b": 2}, source=Path("test2.yaml"))

    config = _merged(Config(entries=[first, other]), Config(entries=[second]))

    assert config.testcases() == [first, other]
    assert first.cls == "pkg.T"
    assert first.params == {"a": 1, "b": 2}
    assert first.source == Path("test.yaml")


def test_earlier_option_only_values_win_over_a_later_regular_entry():
    option = TestCase(name="t", cls="pkg.Option", params={"a": 1}, option_only=True)
    regular = TestCase(name="t", cls="pkg.T", params={"a": 2})

    _merged(Config(entries=[option]), Config(entries=[regular]))

    assert (regular.cls, regular.params) == ("pkg.Option", {"a": 1})


def test_option_only_merge_needs_the_same_kind():
    group = TestGroup(name="x", entries=[])
    option = TestCase(name="x", cls=None, option_only=True)

    config = _merged(Config(entries=[group]), Config(entries=[option]))

    assert config.entries == [group, option]


def test_option_only_merge_follows_the_name_path():
    top = TestCase(name="t", cls="pkg.Top", params={"a": 1})
    nested = TestCase(name="t", cls="pkg.Nested", params={"a": 1})
    group = TestGroup(name="g", entries=[nested])
    option_group = TestGroup(
        name="g", entries=[TestCase(name="t", cls=None, params={"a": 2}, option_only=True)], option_only=True
    )

    config = _merged(Config(entries=[top, group]), Config(entries=[option_group]))

    assert config.entries == [top, group]
    assert top.params == {"a": 1}
    assert nested.params == {"a": 2}


def test_anonymous_groups_do_not_add_to_the_name_path():
    regular = TestCase(name="t", cls="pkg.T", params={"a": 1})
    config = _merged(
        Config(entries=[TestGroup(entries=[regular])]),
        Config(entries=[TestGroup(entries=[TestCase(name="t", cls=None, params={"a": 2}, option_only=True)])]),
    )

    assert regular.params == {"a": 2}
    assert config.testcases() == [regular]


def test_option_only_group_moves_to_the_regular_group():
    option_t1 = TestCase(name="t1", cls=None, params={"a": 2}, option_only=True)
    option_unknown = TestCase(name="unknown", cls=None, option_only=True)
    option_group = TestGroup(name="g", entries=[option_t1, option_unknown], option_only=True)
    t1 = TestCase(name="t1", cls="pkg.T1", params={"a": 1})
    t2 = TestCase(name="t2", cls="pkg.T2")
    group = TestGroup(name="g", entries=[t1, t2], source=Path("test.yaml"))
    other = TestCase(name="other", cls="pkg.Other")

    config = _merged(Config(entries=[option_group]), Config(entries=[other, group]))

    assert config.entries == [other, group]
    assert not group.option_only
    assert group.source == Path("test.yaml")
    assert group.entries == [option_unknown, t1, t2]
    assert t1.params == {"a": 2}
    assert config.testcases() == [other, t1, t2]


def test_option_only_params_replace_fixturemap_entries_and_back():
    regular = TestCase(name="t", cls="pkg.T", params={"psu": "x"}, fixturemap={"dmm": "dmm_1"})
    option = TestCase(name="t", cls=None, params={"dmm": "y"}, fixturemap={"psu": "psu_2"}, option_only=True)

    _merged(Config(entries=[regular]), Config(entries=[option]))

    assert regular.params == {"dmm": "y"}
    assert regular.fixturemap == {"psu": "psu_2"}


def test_option_only_generator_merges_create_group_only_when_given():
    path = ConfigPath(path="data.csv", source=Path("options.yaml"))
    regular = Generator(name="gen", cls="pkg.Gen", params={"a": 1}, create_group=False)
    option = Generator(name="gen", cls=None, params={"file": path}, create_group=None, option_only=True)

    _merged(Config(entries=[regular]), Config(entries=[option]))

    assert regular.cls == "pkg.Gen"
    assert regular.create_group is False
    assert regular.params == {"a": 1, "file": path}

    _merged(Config(entries=[regular]), Config(entries=[Generator(name="gen", cls=None, create_group=True)]))
    assert regular.create_group is True


def test_fixtures_steps_and_named_reports_merge_by_name():
    fixture = Fixture(name="psu", cls="pkg.Psu", autoloaded=True)
    setup = Step(stage="env_setup", name="s", cls="pkg.Setup")
    report = Report(cls="pkg.Report", name="json")
    config = _merged(
        Config(entries=[fixture, setup, report]),
        Config(
            entries=[
                Fixture(name="psu", cls=None, params={"port": "COM2"}),
                Step(stage="env_setup", name="s", cls=None, params={"a": 1}),
                Step(stage="dut_shutdown", name="s", cls="pkg.Shutdown"),
                Report(cls=None, name="json", params={"indent": 2}),
            ]
        ),
    )

    assert config.fixtures() == [fixture]
    assert (fixture.cls, fixture.params, fixture.autoloaded) == ("pkg.Psu", {"port": "COM2"}, True)
    assert [step.stage for step in config.steps()] == ["env_setup", "dut_shutdown"]
    assert setup.params == {"a": 1}
    assert config.reports() == [report]
    assert report.params == {"indent": 2}


def test_unnamed_entries_are_appended_unmerged():
    paths = [PythonPath(path=ConfigPath(path="lib")), PythonPath(path=ConfigPath(path="lib"))]
    reports = [Report(cls="pkg.A"), Report(cls="pkg.A")]
    tests = [TestCase(name=None, cls="pkg.T"), TestCase(name=None, cls="pkg.T")]

    config = _merged(*(Config(entries=[entry]) for entry in paths + reports + tests))

    assert config.entries == paths + reports + tests


def test_validate_requires_name_and_class_of_active_entries():
    Config(entries=[TestCase(name="t", cls=None, option_only=True), TestGroup()]).validate()

    for entry, message in [
        (Fixture(name="f", cls=None), "fixture 'f' has no 'class'"),
        (TestCase(name=None, cls="pkg.T"), "unnamed testcase has no 'name'"),
        (Generator(name="g", cls=None), "generator 'g' has no 'class'"),
        (Step(stage="dut_info", name="s", cls=None), "dut_info 's' has no 'class'"),
        (Report(cls=None, name="r"), "report 'r' has no 'class'"),
        (TestGroup(name="g", entries=[TestCase(name="t", cls=None)]), "testcase 't' has no 'class'"),
    ]:
        with pytest.raises(ConfigError, match=message):
            Config(entries=[entry]).validate()


def test_entries_of_a_new_group_are_merged_with_one_another():
    first = TestCase(name="t", cls="pkg.T")
    group = TestGroup(name="g", entries=[first, TestCase(name="t", cls=None, params={"a": 1})])

    config = _merged(Config(entries=[group]))

    assert group.entries == [first]
    assert first.params == {"a": 1}
