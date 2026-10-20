#
# This module holds the events that flow through the report stream
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Reporting"):
#
# - There are two families of events:
#     * content events, reported by tests (or fixtures) while running:
#       TextEvent, TableEvent, ChartEvent, ImageEvent and VerdictEvent.
#     * lifecycle events, reported only by the framework: RunStarted,
#       GroupStarted/GroupFinished, TestStarted/TestFinished and RunFinished.
#
# - Every event carries a timestamp, the `path` of group names (and the test
#   name, for events inside a test) and the `test` it was reported in. The
#   stream fills in the context, so a reporting call never has to pass it.
#
# - A VerdictEvent is an intermediate verdict a test reports about one check.
#   The test's overall verdict still comes from test(); the runner only lets a
#   reported FAILED verdict downgrade an otherwise PASSED result (see
#   core/runner.py). TestFinished carries that overall verdict.
#
# - Each event class has a `kind` used for dispatch to ReportModule.on_<kind>
#   handlers and as the "event" tag in to_dict().
#

from __future__ import annotations

import time
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar

from fixturerig.base.verdict import Verdict
from fixturerig.report.elements import Chart, Element, Image, Table, Text


@dataclass
class ReportEvent:
    """Base class for everything that flows through a ReportStream."""

    kind: ClassVar[str] = "event"

    timestamp: float = field(default_factory=time.time, kw_only=True)
    path: tuple[str, ...] = field(default=(), kw_only=True)
    test: str | None = field(default=None, kw_only=True)  # the test it was reported in

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"event": self.kind}
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, Element):
                value = value.to_dict()
            elif isinstance(value, Verdict):
                value = {"status": value.status.value, "message": value.message}
            elif isinstance(value, tuple):
                value = list(value)
            data[item.name] = value
        return data


# --- content events ----------------------------------------------------------


@dataclass
class ContentEvent(ReportEvent):
    """Base class for events a test reports while running."""

    @property
    def element(self) -> Element | None:
        return None


@dataclass
class TextEvent(ContentEvent):
    kind: ClassVar[str] = "text"
    text: Text

    @property
    def element(self) -> Element:
        return self.text


@dataclass
class TableEvent(ContentEvent):
    kind: ClassVar[str] = "table"
    table: Table

    @property
    def element(self) -> Element:
        return self.table


@dataclass
class ChartEvent(ContentEvent):
    kind: ClassVar[str] = "chart"
    chart: Chart

    @property
    def element(self) -> Element:
        return self.chart


@dataclass
class ImageEvent(ContentEvent):
    kind: ClassVar[str] = "image"
    image: Image

    @property
    def element(self) -> Element:
        return self.image


@dataclass
class VerdictEvent(ContentEvent):
    """An intermediate verdict about one check inside a test."""

    kind: ClassVar[str] = "verdict"
    verdict: Verdict


# --- lifecycle events --------------------------------------------------------


@dataclass
class LifecycleEvent(ReportEvent):
    """Base class for events only the framework reports."""


@dataclass
class RunStarted(LifecycleEvent):
    kind: ClassVar[str] = "run_started"
    title: str = "FixtureRig test run"


@dataclass
class RunFinished(LifecycleEvent):
    kind: ClassVar[str] = "run_finished"
    counts: dict[str, int] = field(default_factory=dict)  # verdict status value -> number of tests
    duration: float = 0.0

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@dataclass
class GroupStarted(LifecycleEvent):
    kind: ClassVar[str] = "group_started"
    name: str | None = None


@dataclass
class GroupFinished(LifecycleEvent):
    kind: ClassVar[str] = "group_finished"
    name: str | None = None
    duration: float = 0.0


@dataclass
class TestStarted(LifecycleEvent):
    """A test is about to run. Also the test's *specification*: what it does,
    how it is parameterized and which requirements it traces to."""

    __test__: ClassVar[bool] = False  # not a pytest test class

    kind: ClassVar[str] = "test_started"
    name: str = ""
    cls: str = ""
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    traceability: list[str] = field(default_factory=list)


@dataclass
class TestFinished(LifecycleEvent):
    __test__: ClassVar[bool] = False

    kind: ClassVar[str] = "test_finished"
    name: str = ""
    verdict: Verdict = field(default_factory=lambda: Verdict(False))
    duration: float = 0.0
    traceability: list[str] = field(default_factory=list)


def _all_kinds(cls: type) -> set[str]:
    kinds = set()
    for sub in cls.__subclasses__():
        if sub.kind != cls.kind:
            kinds.add(sub.kind)
        kinds |= _all_kinds(sub)
    return kinds


# Every concrete event kind, e.g. for validating a module's `exclude` list.
EVENT_KINDS: frozenset[str] = frozenset(_all_kinds(ReportEvent))
CONTENT_KINDS: frozenset[str] = frozenset(_all_kinds(ContentEvent))
