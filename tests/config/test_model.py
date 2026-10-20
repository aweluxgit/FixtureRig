from pathlib import Path

from fixturerig.config.model import Config, Fixture, TestCase, TestGroup


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
