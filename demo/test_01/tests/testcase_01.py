from fixturerig.base import TestCase
from fixturerig.report import report


class TestCase01(TestCase):
    """
    Example testcase for testing the framework.
    """
    def test(self):
        report.text(f"Welcome to FixturRig.")
        return True
