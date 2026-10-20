import pytest

from fixturerig.base import TestCase as BaseTestCase  # aliased so pytest does not collect it
from fixturerig.base import VerdictStatus
from fixturerig.config.model import Config
from fixturerig.config.model import Fixture as FixtureEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.core.runner import run_tests
from fixturerig.fixtures.dummy_fixture import DummyFixture

INSTANCES: list[DummyFixture] = []


class UsesDummy(BaseTestCase):
    def __init__(self, dummy: DummyFixture):
        INSTANCES.append(dummy)
        self.dummy = dummy

    def test(self):
        self.dummy.write("voltage", 4.5)
        return self.dummy.read("voltage") == 4.5


@pytest.fixture(autouse=True)
def _reset():
    INSTANCES.clear()


def _config(**fixture_params) -> Config:
    return Config(
        entries=[
            FixtureEntry(name="dummy", cls="fixturerig.fixtures.dummy_fixture.DummyFixture", params=fixture_params),
            TestCaseEntry(name="t", cls=f"{__name__}.UsesDummy", params={"dummy": "dummy"}),
        ]
    )


def test_registers_read_back_what_was_written():
    dummy = DummyFixture(values={"current": "0.5"})
    dummy.setup()
    dummy.write("voltage", 3)
    assert dummy.read("voltage") == 3.0
    assert dummy.read("current") == 0.5


def test_unknown_register_lists_known_ones():
    dummy = DummyFixture(values={"voltage": 0})
    dummy.setup()
    with pytest.raises(KeyError, match="known: voltage"):
        dummy.read("current")


def test_access_requires_a_connection():
    dummy = DummyFixture()
    with pytest.raises(RuntimeError, match="not connected"):
        dummy.write("voltage", 1)
    dummy.setup()
    dummy.teardown()
    with pytest.raises(RuntimeError, match="not connected"):
        dummy.read("voltage")


def test_runner_drives_the_full_lifecycle():
    (result,) = run_tests(_config(values={"voltage": 0.0}))

    assert result.passed
    assert INSTANCES[0].calls == ["setup", "self_test", "start", "stop", "lazy_stop", "disconnect", "teardown"]


def test_failing_self_test_skips_dependent_tests():
    (result,) = run_tests(_config(self_test_ok=False))
    assert result.verdict.status is VerdictStatus.SKIPPED
    assert "self test" in result.verdict.message
