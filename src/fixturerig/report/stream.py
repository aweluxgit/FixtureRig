#
# This module holds the report stream that connects reporters to report modules
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Reporting"):
#
# - A ReportStream fans every event out to the attached report modules that
#   accept it. It is the only channel between tests and reports: tests never
#   talk to a report module directly.
#
# - The stream tracks the current context (open groups, running test) from
#   the lifecycle events passing through it, and stamps every event with it.
#   So `report().text("...")` needs no context arguments.
#
# - The stream also remembers the verdicts reported during the current test,
#   so the runner can fold them into the overall verdict.
#
# - A report module that raises while handling an event or closing is logged
#   and skipped. It is never allowed to change a test's outcome or abort the
#   run.
#
# - Events are dispatched under a lock, so a test that reports from several
#   threads (e.g. a monitoring thread) still gives every module an ordered,
#   non-interleaved sequence.
#
# - Global access: the runner activates its stream for the duration of the
#   run, and `report()` returns it. Outside a run, `report()` returns a
#   default stream with a ConsoleReport, so a test class used as a library
#   (or from a REPL) still shows its output. A plain module level variable is
#   used rather than a ContextVar, because threads a test starts do not
#   inherit ContextVars.
#

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterable, Iterator, Sequence

from fixturerig.base.verdict import Verdict, VerdictStatus
from fixturerig.report.elements import Cell, Chart, Image, Series, Table, Text
from fixturerig.report.events import (
    ChartEvent,
    GroupFinished,
    GroupStarted,
    ImageEvent,
    ReportEvent,
    TableEvent,
    TestFinished,
    TestStarted,
    TextEvent,
    VerdictEvent,
)
from fixturerig.report.module import ReportModule

logger = logging.getLogger(__name__)

# Statuses a test may report about one of its checks.
_REPORTABLE = {VerdictStatus.PASSED, VerdictStatus.FAILED, VerdictStatus.SKIPPED}


class ReportStream:
    """Distributes report events to every attached report module."""

    def __init__(self, modules: Iterable[ReportModule] = ()):
        self._modules: list[ReportModule] = list(modules)
        self._lock = threading.RLock()
        self._groups: list[str | None] = []
        self._test: str | None = None
        self._test_verdicts: list[Verdict] = []
        self._closed = False

    # --- module management ---------------------------------------------------

    @property
    def modules(self) -> list[ReportModule]:
        return list(self._modules)

    def attach(self, module: ReportModule) -> None:
        with self._lock:
            self._modules.append(module)

    def detach(self, module: ReportModule) -> None:
        with self._lock:
            self._modules.remove(module)

    # --- context ---------------------------------------------------------------

    @property
    def path(self) -> tuple[str, ...]:
        """Names of the open groups, plus the running test if there is one."""
        names = [name for name in self._groups if name is not None]
        if self._test is not None:
            names.append(self._test)
        return tuple(names)

    @property
    def current_test(self) -> str | None:
        return self._test

    def reported_verdicts(self) -> list[Verdict]:
        """Verdicts reported via verdict() since the current test started."""
        with self._lock:
            return list(self._test_verdicts)

    # --- dispatch --------------------------------------------------------------

    def emit(self, event: ReportEvent) -> ReportEvent:
        """Stamp `event` with the current context and hand it to every module."""
        with self._lock:
            if isinstance(event, GroupStarted):
                self._groups.append(event.name)
            elif isinstance(event, TestStarted):
                self._test = event.name
                self._test_verdicts = []
            elif isinstance(event, VerdictEvent) and self._test is not None:
                self._test_verdicts.append(event.verdict)

            event.path = self.path
            event.test = self._test

            if isinstance(event, GroupFinished) and self._groups:
                self._groups.pop()
            elif isinstance(event, TestFinished):
                self._test = None

            for module in self._modules:
                try:
                    if module.accepts(event):
                        module.handle(event)
                except Exception:
                    logger.exception(
                        "Report module %s failed to handle a %r event",
                        type(module).__name__,
                        event.kind,
                    )
        return event

    def close(self) -> None:
        """Close every attached module. Safe to call more than once."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for module in self._modules:
                try:
                    module.close()
                except Exception:
                    logger.exception("Report module %s failed to close", type(module).__name__)

    # --- reporting API for tests -------------------------------------------------

    def text(self, text: str) -> None:
        """Report a block of text."""
        self.emit(TextEvent(Text(text)))

    def table(
        self,
        rows: Table | Sequence[Sequence[Cell]],
        headers: Sequence[str] | None = None,
        title: str | None = None,
    ) -> None:
        """Report a table, given as a Table or as rows of cells.

        Cells may be scalars (a simple table) or report elements, including
        other tables (a complex table).
        """
        if not isinstance(rows, Table):
            rows = Table(list(rows), list(headers) if headers is not None else None, title)
        elif headers is not None or title is not None:
            raise TypeError("headers/title are taken from the Table when one is passed")
        self.emit(TableEvent(rows))

    def chart(
        self,
        chart: Chart | str,
        series: Sequence[Series] | dict[str, tuple[Sequence[float], Sequence[float]]] = (),
        x_label: str = "",
        y_label: str = "",
        kind: str = "line",
    ) -> None:
        """Report a chart, given as a Chart or as a title plus series.

        `series` may be Series objects or a ``{name: (x_values, y_values)}`` mapping.
        """
        if not isinstance(chart, Chart):
            if isinstance(series, dict):
                series = [Series(name, x, y) for name, (x, y) in series.items()]
            chart = Chart(chart, list(series), x_label, y_label, kind)
        self.emit(ChartEvent(chart))

    def image(self, image: Image | str, caption: str = "", mime_type: str = "image/png") -> None:
        """Report an image, given as an Image or a file path."""
        if not isinstance(image, Image):
            image = Image(path=image, caption=caption, mime_type=mime_type)
        self.emit(ImageEvent(image))

    def verdict(self, verdict: Verdict | bool | str, message: str = "") -> Verdict:
        """Report an intermediate verdict about one check and return it.

        A reported FAILED verdict makes the test fail even if test() returns
        True. Only passed/failed/skipped may be reported; the other statuses
        are reserved for the runner.
        """
        if not isinstance(verdict, Verdict):
            verdict = Verdict(verdict, message)
        elif message:
            verdict = Verdict(verdict.status, message)
        if verdict.status not in _REPORTABLE:
            raise ValueError(f"A test cannot report a {verdict.status.value!r} verdict")
        self.emit(VerdictEvent(verdict))
        return verdict

    def check(self, condition: bool, message: str = "") -> bool:
        """Report a passed/failed verdict for `condition` and return it."""
        self.verdict(bool(condition), message)
        return bool(condition)

    # --- global access -------------------------------------------------------------

    @contextmanager
    def activate(self) -> Iterator["ReportStream"]:
        """Make this the stream returned by report() for the duration of the block."""
        global _active
        previous = _active
        _active = self
        try:
            yield self
        finally:
            _active = previous


_active: ReportStream | None = None
_default: ReportStream | None = None
_default_lock = threading.Lock()


def report() -> ReportStream:
    """Return the report stream of the running test run.

    Use it from a test to add content to every active report::

        from fixturerig.report import report

        def test(self):
            report().text("Ramping supply")
            report().table([["U", 4.9]], headers=["Signal", "Value"])
            return report().check(voltage < self.limit, f"U = {voltage} V")

    Outside a run this returns a default stream that prints to the console.
    """
    if _active is not None:
        return _active
    global _default
    with _default_lock:
        if _default is None:
            from fixturerig.report.console import ConsoleReport

            _default = ReportStream([ConsoleReport()])
        return _default
