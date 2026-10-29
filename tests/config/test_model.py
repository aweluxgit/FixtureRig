from pathlib import Path

import pytest

from fixturerig.config.model import Config, ConfigError, Fixture, Step, TestCase, TestGroup


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
