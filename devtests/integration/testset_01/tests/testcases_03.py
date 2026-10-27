from fixturerig.base import TestCase, Verdict, VerdictException, VerdictStatus
from fixturerig.report import report


class TestCase0301(TestCase):
    """
    Test spec 3.1: test() neither reports nor returns a verdict.
    Expected verdict: none
    """
    def test(self):
        report.text("Returning without any verdict")


class TestCase030201(TestCase):
    """
    Test spec 3.2.1: a passed verdict is reported via report.verdict().
    Expected verdict: passed
    """
    def test(self):
        report.verdict(VerdictStatus.PASSED, "Reported passed verdict")


class TestCase030202(TestCase):
    """
    Test spec 3.2.2: a failed verdict is reported via report.verdict().
    The reported verdict downgrades the returned True.
    Expected verdict: failed
    """
    def test(self):
        report.verdict(VerdictStatus.FAILED, "Reported failed verdict")


class TestCase030203(TestCase):
    """
    Test spec 3.2.3: an error verdict is reported via report.verdict().
    Only the runner may set error, so the report raises.
    Expected verdict: error
    """
    def test(self):
        report.verdict(VerdictStatus.ERROR, "Reported error verdict")


class TestCase030301(TestCase):
    """
    Test spec 3.3.1: test() returns a passed Verdict.
    Expected verdict: passed
    """
    def test(self):
        return Verdict(VerdictStatus.PASSED, "Returned passed verdict")


class TestCase030302(TestCase):
    """
    Test spec 3.3.2: test() returns a failed Verdict.
    Expected verdict: failed
    """
    def test(self):
        return Verdict(VerdictStatus.FAILED, "Returned failed verdict")


class TestCase030303(TestCase):
    """
    Test spec 3.3.3: test() returns an error Verdict.
    Expected verdict: error
    """
    def test(self):
        return Verdict(VerdictStatus.ERROR, "Returned error verdict")


class TestCase030304(TestCase):
    """
    Test spec 3.3.4: test() returns True.
    Expected verdict: passed
    """
    def test(self):
        return True


class TestCase030305(TestCase):
    """
    Test spec 3.3.5: test() returns False.
    Expected verdict: failed
    """
    def test(self):
        return False


class TestCase030401(TestCase):
    """
    Test spec 3.4.1: test() raises a VerdictException with a passed verdict.
    Expected verdict: passed
    """
    def test(self):
        raise VerdictException(Verdict(VerdictStatus.PASSED), "Raised passed verdict")


class TestCase030402(TestCase):
    """
    Test spec 3.4.2: test() raises a VerdictException with a failed verdict.
    Expected verdict: failed
    """
    def test(self):
        raise VerdictException(Verdict(VerdictStatus.FAILED), "Raised failed verdict")


class TestCase030403(TestCase):
    """
    Test spec 3.4.3: test() raises a VerdictException with an error verdict.
    Expected verdict: error
    """
    def test(self):
        raise VerdictException(Verdict(VerdictStatus.ERROR), "Raised error verdict")


class TestCase030501(TestCase):
    """
    Test spec 3.5.1: a reported failed verdict trumps reported and returned passed verdicts.
    Expected verdict: failed
    """
    def test(self):
        report.passed("Reported passed verdict")
        report.failed("Reported failed verdict")
        report.passed("Reported passed verdict")
        return True


class TestCase030502(TestCase):
    """
    Test spec 3.5.2: an exception trumps reported passed and failed verdicts.
    Expected verdict: error
    """
    def test(self):
        report.passed("Reported passed verdict")
        report.failed("Reported failed verdict")
        raise RuntimeError("Raised exception after reported verdicts")
