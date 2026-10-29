import pytest

from fixturerig.base import Fixture
from fixturerig.base import Generator as BaseGenerator
from fixturerig.base import TestCase as BaseTestCase  # aliased so pytest does not collect it
from fixturerig.config.model import Config, ConfigError, Generator, TestGroup
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.core.generator import GeneratorError, run_generators
from fixturerig.core.runner import run_tests


def cls_path(cls: type) -> str:
    return f"{__name__}.{cls.__name__}"


# --- test doubles, loaded by dotted name ------------------------------------


class AboveLimit(BaseTestCase):
    def test(self, value: float, limit: float):
        return value > limit


class Sweep(BaseGenerator):
    def __init__(self, limit: float = 1.0):
        self.limit = limit

    def generate(self, values: list[float]):
        return [
            TestCaseEntry(name=f"value_{v}", cls=cls_path(AboveLimit), params={"value": v, "limit": self.limit})
            for v in values
        ]


class Grouped(BaseGenerator):
    def generate(self):
        return [TestGroup(name="g", entries=[TestCaseEntry(name="t", cls=cls_path(AboveLimit))])]


class Nested(BaseGenerator):
    def generate(self):
        return [Generator(cls=cls_path(Sweep), name="inner", params={"values": [2]})]


class Psu(Fixture):
    pass


class WantsFixture(BaseGenerator):
    def generate(self, psu: Psu):
        return []


class ReturnsFixture(BaseGenerator):
    def generate(self):
        from fixturerig.config.model import Fixture as FixtureEntry

        return [FixtureEntry(name="psu", cls=cls_path(Psu))]


class ReturnsTuple(BaseGenerator):
    def generate(self):
        return ()


class Crashes(BaseGenerator):
    def generate(self):
        raise RuntimeError("boom")


class NotAGenerator:
    def generate(self):
        return []


COUNT = {"calls": 0}


class Counting(BaseGenerator):
    def generate(self):
        COUNT["calls"] += 1
        return []


# --- tests -------------------------------------------------------------------


def test_generator_without_group_adds_entries_directly():
    gen = Generator(
        name="sweep", cls=cls_path(Sweep), params={"values": [0.5, 2.0], "limit": 1.5}, create_group=False
    )
    config = Config(entries=[gen])

    run_generators(config)

    assert gen.generated
    assert [e.name for e in gen.entries] == ["value_0.5", "value_2.0"]
    assert gen.entries[1].params == {"value": 2.0, "limit": 1.5}
    assert [t.name for t in config.testcases()] == ["value_0.5", "value_2.0"]


def test_generator_wraps_entries_in_a_group_by_default():
    gen = Generator(cls=cls_path(Sweep), name="sweep", params={"values": [3]})

    run_generators(Config(entries=[gen]))

    (group,) = gen.entries
    assert isinstance(group, TestGroup)
    assert group.name == "sweep"
    assert [e.name for e in group.entries] == ["value_3.0"]


def test_generated_groups_and_nested_generators_are_expanded(tmp_path):
    source = tmp_path / "config.yaml"
    grouped = Generator(name="grouped", cls=cls_path(Grouped), source=source, create_group=False)
    nested = Generator(name="nested", cls=cls_path(Nested), source=source)
    config = Config(entries=[TestGroup(entries=[grouped]), nested])

    run_generators(config)

    assert grouped.entries[0].entries[0].source == source
    inner = nested.entries[0].entries[0]
    assert inner.generated and inner.source == source
    assert [t.name for t in config.testcases()] == ["t", "value_2.0"]


def test_generators_run_only_once():
    COUNT["calls"] = 0
    config = Config(entries=[Generator(name="counting", cls=cls_path(Counting))])

    run_generators(config)
    run_generators(config)

    assert COUNT["calls"] == 1


@pytest.mark.parametrize(
    "entry, message",
    [
        (Generator(name="gen", cls=cls_path(Sweep)), "Missing required parameter: 'values'"),
        (Generator(name="gen", cls=cls_path(Sweep), params={"values": [], "typo": 1}), "Unknown parameter"),
        (Generator(name="gen", cls=cls_path(WantsFixture), params={"psu": "psu"}), "fixture reference"),
        (Generator(name="gen", cls=cls_path(ReturnsFixture)), "may only return"),
        (Generator(name="gen", cls=cls_path(ReturnsTuple)), "must return a list"),
        (Generator(name="gen", cls=cls_path(Crashes)), "boom"),
        (Generator(name="gen", cls=cls_path(NotAGenerator)), "not a subclass"),
        (Generator(name="gen", cls="no.such.Module"), "no.such.Module"),
    ],
)
def test_generator_problems_are_config_errors(entry, message):
    with pytest.raises(GeneratorError, match=message) as info:
        run_generators(Config(entries=[entry]))
    assert isinstance(info.value, ConfigError)


def test_run_tests_runs_generated_tests_in_place():
    config = Config(
        entries=[
            TestCaseEntry(name="first", cls=cls_path(AboveLimit), params={"value": 2, "limit": 1}),
            Generator(cls=cls_path(Sweep), name="sweep", params={"values": [0.5, 2.0]}),
            TestCaseEntry(name="last", cls=cls_path(AboveLimit), params={"value": 0, "limit": 1}),
        ]
    )

    results = run_tests(config)

    assert [(r.name, r.verdict.status.value) for r in results] == [
        ("first", "passed"),
        ("value_0.5", "failed"),
        ("value_2.0", "passed"),
        ("last", "failed"),
    ]
