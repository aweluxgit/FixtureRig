from fixturerig.base import TestCase
from fixturerig.fixtures.dummy_fixture import DummyFixture
from fixturerig.report import report


class InheritanceBase(TestCase):
    """
    Base class for the inheritance tests: test() takes param1 and param2 and
    checks their converted types.
    """
    def test(self, param1: int, param2: float):
        report.text(f"Assert that inherited parameters are mapped and converted by the base class hints")
        ok = report.check(isinstance(param1, int), f"Instance of param1 is {type(param1)} with value {param1}")
        ok &= report.check(isinstance(param2, float), f"Instance of param2 is {type(param2)} with value {param2}")
        return ok


class TestCase0201(InheritanceBase):
    """
    Test spec 2.1: test() is inherited unchanged
    """


class TestCase0202(InheritanceBase):
    """
    Test spec 2.2: test() is overridden and declares every parameter explicitly.
    Also confirms that the child class parameter types have precedence
    """
    def test(self, param1: float, param2: int, param3: str):
        report.text("Calling super with int/float mapping swapped")
        ok = super().test(int(param1), float(param2))
        report.text("Check parameter types passed to this function.")
        ok &= report.check(isinstance(param1, float), f"Instance of param1 is {type(param1)} with value {param1}")
        ok &= report.check(isinstance(param2, int), f"Instance of param2 is {type(param2)} with value {param2}")
        ok &= report.check(isinstance(param3, str), f"Instance of param3 is {type(param3)} with value {param3}")
        return ok


class TestCase0203(InheritanceBase):
    """
    Test spec 2.3: test() only declares param3 and forwards **kwargs, so
    param1 and param2 are found in the base class test()
    """
    def test(self, param3: str, **kwargs):
        ok = super().test(**kwargs)
        ok &= report.check(isinstance(param3, str), f"Instance of param3 is {type(param3)} with value {param3}")
        return ok
