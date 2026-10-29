from fixturerig.base import TestCase
from fixturerig.report import report


class MergedParameterTest(TestCase):
    """
    Base class for the merge tests: test() requires `a`, which is only given
    by a second entry with the same name path. Without the merge the test
    would be skipped for the missing parameter.
    """
    def test(self, a: int):
        report.text("Assert that the parameter of the merged entry arrives")
        return report.check(a == 1, f"Value of a is {a!r}")


class TestCase0501(MergedParameterTest):
    """
    Test spec 5.1: the class and the parameter are given by two entries with
    the same name in the same group of test.yaml.
    Expected verdict: passed
    """


class TestCase0502(MergedParameterTest):
    """
    Test spec 5.2: the class is given in test.yaml, the parameter by an entry
    with the same name path in test2.yaml.
    Expected verdict: passed
    """
