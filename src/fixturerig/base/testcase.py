"""Base class for user-defined FixtureRig test cases."""

from __future__ import annotations

from fixturerig.base.verdict import Verdict


class TestCase:
    """Common lifecycle interface for a single executable test case.

    Subclasses implement :meth:`test`. ``setup`` and ``teardown`` are
    optional hooks and default to no-ops. The test result is a boolean or a
    :class:`Verdict`; exceptions are left for the runner to classify.
    """

    def setup(self) -> None:
        """Prepare this testcase before execution."""

    def test(self) -> bool | Verdict:
        """Run the testcase and return its pass/fail verdict."""
        raise NotImplementedError("TestCase subclasses must implement test().")

    def teardown(self) -> None:
        """Release testcase-owned resources after execution."""
