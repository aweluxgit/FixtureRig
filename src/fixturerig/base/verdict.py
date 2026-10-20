"""Verdict values and exceptions used by FixtureRig test cases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VerdictStatus(str, Enum):
    """The possible outcomes for a testcase."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    NONE = "none"
    KNOWNFAILED = "knownfailed"


@dataclass(frozen=True)
class Verdict:
    """A testcase outcome, optionally accompanied by an explanation.

    Test implementations can return ``PASSED``, ``FAILED``, or ``SKIPPED``.
    The runner uses ``ERROR`` and ``NONE`` for execution problems, and
    ``KNOWNFAILED`` for tests registered as expected to fail.

    A boolean is accepted for compatibility: ``True`` maps to ``PASSED`` and
    ``False`` maps to ``FAILED``.

    Example::

        return Verdict(VerdictStatus.FAILED, "Voltage exceeded the limit")
    """

    status: VerdictStatus
    message: str = ""

    def __post_init__(self) -> None:
        status = self.status
        if isinstance(status, bool):
            status = VerdictStatus.PASSED if status else VerdictStatus.FAILED
        elif isinstance(status, str):
            try:
                status = VerdictStatus(status.lower())
            except ValueError as exc:
                allowed = ", ".join(item.value for item in VerdictStatus)
                raise ValueError(f"Unknown verdict {status!r}; expected one of: {allowed}") from exc
        elif not isinstance(status, VerdictStatus):
            raise TypeError("Verdict.status must be a VerdictStatus, string, or bool")

        if not isinstance(self.message, str):
            raise TypeError("Verdict.message must be a string")
        object.__setattr__(self, "status", status)

    @property
    def passed(self) -> bool:
        """Whether the testcase outcome is a plain pass."""
        return self.status is VerdictStatus.PASSED

    def __str__(self) -> str:
        return f"{self.status.value}: {self.message}" if self.message else self.status.value

    def __repr__(self) -> str:
        return f"Verdict(status={self.status.value!r}, message={self.message!r})"


class VerdictException(Exception):
    """Raise this from ``TestCase.test()`` to return a deliberate verdict."""

    def __init__(self, verdict: Verdict | bool, message: str = "") -> None:
        if isinstance(verdict, bool):
            verdict = Verdict(verdict, message)
        elif not isinstance(verdict, Verdict):
            raise TypeError("verdict must be a Verdict or bool")
        elif message:
            verdict = Verdict(verdict.status, message)

        self.verdict = verdict
        super().__init__(str(verdict))
