"""Public base classes and verdict types for FixtureRig extensions."""

from fixturerig.base.fixture import Fixture
from fixturerig.base.testcase import TestCase
from fixturerig.base.verdict import Verdict, VerdictException, VerdictStatus

__all__ = ["Fixture", "TestCase", "Verdict", "VerdictException", "VerdictStatus"]
