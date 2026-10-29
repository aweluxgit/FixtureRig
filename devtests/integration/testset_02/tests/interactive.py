# Test doubles for the --interactive check. They print markers to stdout that
# run_testset.sh / run_testset.bat look for.

from fixturerig.base import Step, TestCase


class InteractiveProbeError(Exception):
    """Raised by Raises; must reach the top of the program with --interactive."""


class Passes(TestCase):
    """
    Test spec 1: a passing test before the failing one runs normally.
    """
    def test(self):
        print("MARKER: test 1 ran")
        return True


class Raises(TestCase):
    """
    Test spec 2: an exception in test().
    Expected without --interactive: the test is reported ERROR and the run goes on.
    Expected with --interactive: the exception ends the program with a traceback.
    """
    def test(self):
        raise InteractiveProbeError("raised on purpose by testset_02")


class NeverRuns(TestCase):
    """
    Test spec 3: a test after the failing one.
    Expected with --interactive: it never runs.
    """
    def test(self):
        print("MARKER: test 3 ran")
        return True


class PowerOff(Step):
    """
    dut_shutdown step: runs even when --interactive ends the run, so the DUT
    is left in a safe state.
    """
    def run(self):
        print("MARKER: dut_shutdown ran")
