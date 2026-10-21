"""Reporting: the report stream, report content and report modules.

Tests report through the global stream::

    from fixturerig.report import report

    report.text("Ramping supply to 5 V")
    report.table([["U", 4.93], ["I", 0.21]], headers=["Signal", "Value"])
    report.chart("Ramp", {"U": (times, volts)}, x_label="s", y_label="V")
    report.check(volts[-1] < 5.1, "final voltage below 5.1 V")

Report modules (console, JSON, HTML, Allure, Excel, PDF, test spec PDF) are
configured with ``report`` entries and receive every event they accept. The
optional ``fixturerig.report.excel`` and ``fixturerig.report.pdf`` modules
need the ``excel`` / ``pdf`` extras and are not imported here.
"""

from fixturerig.report.console import ColoredConsoleReport, ConsoleReport
from fixturerig.report.elements import Chart, Element, Image, Series, Table, Text
from fixturerig.report.events import (
    ChartEvent,
    ContentEvent,
    GroupFinished,
    GroupStarted,
    ImageEvent,
    LifecycleEvent,
    ReportEvent,
    RunFinished,
    RunStarted,
    TableEvent,
    TestFinished,
    TestStarted,
    TextEvent,
    VerdictEvent,
)
from fixturerig.report.module import ReportModule
from fixturerig.report.recording import RecordingReport
from fixturerig.report.stream import ReportStream, current_stream, report

__all__ = [
    "Chart",
    "ChartEvent",
    "ColoredConsoleReport",
    "ConsoleReport",
    "ContentEvent",
    "Element",
    "GroupFinished",
    "GroupStarted",
    "Image",
    "ImageEvent",
    "LifecycleEvent",
    "RecordingReport",
    "ReportEvent",
    "ReportModule",
    "ReportStream",
    "RunFinished",
    "RunStarted",
    "Series",
    "Table",
    "TableEvent",
    "TestFinished",
    "TestStarted",
    "Text",
    "TextEvent",
    "VerdictEvent",
    "current_stream",
    "report",
]
