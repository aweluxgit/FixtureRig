#
# This module holds the console report modules
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Reporting"):
#
# - ConsoleReport is active by default: when the configuration declares no
#   report module that is a ConsoleReport (ColoredConsoleReport included),
#   one is added with default settings (see report/loader.py). To make the
#   console quieter, configure one explicitly with a lower `verbosity`.
#
# - verbosity: 0 = run summary only, 1 = + groups and test verdicts,
#   2 = + everything tests report (text, tables, charts, images, checks).
#
# - Output is plain ASCII so it renders on any terminal, including Windows
#   consoles with legacy code pages. Output goes to `output`, or to the
#   sys.stdout current at write time (so capturing tools keep working).
#

from __future__ import annotations

import sys
from typing import TextIO

from fixturerig.base.verdict import VerdictStatus
from fixturerig.report.events import (
    ContentEvent,
    GroupFinished,
    GroupStarted,
    RunFinished,
    RunStarted,
    TestFinished,
    TestStarted,
    VerdictEvent,
)
from fixturerig.report.module import ReportModule

_INDENT = "  "


class ConsoleReport(ReportModule):
    """Prints the run as an indented, human-readable log.

    :param verbosity: 0 = summary only, 1 = groups and verdicts, 2 = all content.
    :param output: the text stream to write to; defaults to ``sys.stdout``.
    """

    def __init__(self, verbosity: int = 2, output: TextIO | None = None, **kwargs):
        super().__init__(**kwargs)
        if verbosity not in (0, 1, 2):
            raise ValueError(f"verbosity must be 0, 1 or 2, got {verbosity!r}")
        self.verbosity = verbosity
        self.output = output
        self._depth = 0

    # --- formatting hooks (overridden by ColoredConsoleReport) ----------------

    def style_status(self, status: VerdictStatus, text: str) -> str:
        return text

    def style_heading(self, text: str) -> str:
        return text

    # --- output -------------------------------------------------------------------

    def write(self, text: str, depth: int | None = None) -> None:
        prefix = _INDENT * (self._depth if depth is None else depth)
        stream = self.output if self.output is not None else sys.stdout
        for line in text.splitlines() or [""]:
            stream.write(f"{prefix}{line}\n")
        stream.flush()

    # --- handlers -----------------------------------------------------------------

    def on_run_started(self, event: RunStarted) -> None:
        if self.verbosity >= 1:
            self.write(self.style_heading(f"=== {event.title} ==="), depth=0)

    def on_group_started(self, event: GroupStarted) -> None:
        if self.verbosity >= 1:
            self.write(self.style_heading(f"> {event.name or '(group)'}"))
        self._depth += 1

    def on_group_finished(self, event: GroupFinished) -> None:
        self._depth = max(0, self._depth - 1)

    def on_test_started(self, event: TestStarted) -> None:
        if self.verbosity >= 2:
            refs = f" [{', '.join(event.traceability)}]" if event.traceability else ""
            self.write(f"- {event.name} ({event.cls}){refs}")

    def on_test_finished(self, event: TestFinished) -> None:
        if self.verbosity >= 1:
            status = event.verdict.status
            label = self.style_status(status, f"[{status.value.upper()}]")
            message = f": {event.verdict.message}" if event.verdict.message else ""
            self.write(f"{label} {event.name} ({event.duration:.3f}s){message}")

    def on_verdict(self, event: VerdictEvent) -> None:
        if self.verbosity >= 2:
            status = event.verdict.status
            mark = self.style_status(status, f"({status.value})")
            self.write(f"{mark} {event.verdict.message}".rstrip(), self._content_depth())

    def on_event(self, event) -> None:
        if isinstance(event, ContentEvent) and event.element is not None and self.verbosity >= 2:
            self.write(event.element.to_text(), self._content_depth())

    def on_run_finished(self, event: RunFinished) -> None:
        parts = [
            self.style_status(VerdictStatus(status), f"{count} {status}")
            for status, count in event.counts.items()
            if count
        ]
        summary = ", ".join(parts) if parts else "no tests"
        self.write(
            self.style_heading(f"=== {summary} ({event.total} test(s) in {event.duration:.2f}s) ==="),
            depth=0,
        )

    def _content_depth(self) -> int:
        return self._depth + 1


_ANSI = {
    VerdictStatus.PASSED: "\033[32m",
    VerdictStatus.FAILED: "\033[31m",
    VerdictStatus.ERROR: "\033[1;31m",
    VerdictStatus.SKIPPED: "\033[33m",
    VerdictStatus.NONE: "\033[35m",
    VerdictStatus.KNOWNFAILED: "\033[36m",
}
_BOLD = "\033[1m"
_RESET = "\033[0m"


class ColoredConsoleReport(ConsoleReport):
    """A ConsoleReport that colors verdicts with ANSI escape codes.

    Colors are only used when the output is a terminal, unless `force_color`
    is set. All ConsoleReport parameters (e.g. `verbosity`) are accepted too.
    """

    def __init__(self, force_color: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.force_color = force_color

    def _colored(self) -> bool:
        if self.force_color:
            return True
        stream = self.output if self.output is not None else sys.stdout
        return bool(getattr(stream, "isatty", lambda: False)())

    def style_status(self, status: VerdictStatus, text: str) -> str:
        return f"{_ANSI[status]}{text}{_RESET}" if self._colored() else text

    def style_heading(self, text: str) -> str:
        return f"{_BOLD}{text}{_RESET}" if self._colored() else text
