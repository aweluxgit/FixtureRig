#
# This module holds a base class for report modules that write a whole
# document at the end of the run
#
# Design decision: file based reports (JSON, HTML, PDF, Excel, Allure) all
# need the event stream as a tree - run -> groups -> tests -> content - rather
# than as a flat sequence. RecordingReport builds that tree from the events it
# accepts and calls write(run) from close(). A run aborted before RunFinished
# is still written, with whatever was recorded until then.
#

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Union

from fixturerig.base.verdict import VerdictStatus
from fixturerig.report.events import (
    ContentEvent,
    GroupFinished,
    GroupStarted,
    ReportEvent,
    RunFinished,
    RunStarted,
    TestFinished,
    TestStarted,
)
from fixturerig.report.module import ReportModule


@dataclass
class TestRecord:
    """One test: its specification, its reported content and its outcome."""

    __test__ = False  # not a pytest test class

    started: TestStarted
    content: list[ContentEvent] = field(default_factory=list)
    finished: TestFinished | None = None

    @property
    def name(self) -> str:
        return self.started.name

    @property
    def status(self) -> VerdictStatus | None:
        return self.finished.verdict.status if self.finished is not None else None


@dataclass
class GroupRecord:
    """A test group, or the run's root. Children keep their reporting order."""

    name: str | None = None
    children: list[Union["GroupRecord", TestRecord, ContentEvent]] = field(default_factory=list)
    started: GroupStarted | None = None
    finished: GroupFinished | None = None

    def tests(self) -> Iterator[TestRecord]:
        """Every test in this group and its subgroups, in order."""
        for child in self.children:
            if isinstance(child, TestRecord):
                yield child
            elif isinstance(child, GroupRecord):
                yield from child.tests()


@dataclass
class RunRecord:
    root: GroupRecord = field(default_factory=GroupRecord)
    started: RunStarted | None = None
    finished: RunFinished | None = None

    @property
    def title(self) -> str:
        return self.started.title if self.started is not None else RunStarted().title

    def tests(self) -> list[TestRecord]:
        return list(self.root.tests())

    def counts(self) -> dict[str, int]:
        """Number of tests per verdict status, including tests that never finished."""
        if self.finished is not None:
            return dict(self.finished.counts)
        counts: dict[str, int] = {}
        for test in self.tests():
            key = test.status.value if test.status is not None else VerdictStatus.NONE.value
            counts[key] = counts.get(key, 0) + 1
        return counts


class RecordingReport(ReportModule):
    """Base class for modules that render the recorded run in close()."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.run = RunRecord()
        self._groups: list[GroupRecord] = [self.run.root]
        self._test: TestRecord | None = None
        self._written = False

    def handle(self, event: ReportEvent) -> None:
        if isinstance(event, RunStarted):
            self.run.started = event
        elif isinstance(event, RunFinished):
            self.run.finished = event
        elif isinstance(event, GroupStarted):
            group = GroupRecord(name=event.name, started=event)
            self._groups[-1].children.append(group)
            self._groups.append(group)
        elif isinstance(event, GroupFinished):
            if len(self._groups) > 1:
                self._groups.pop().finished = event
        elif isinstance(event, TestStarted):
            self._test = TestRecord(started=event)
            self._groups[-1].children.append(self._test)
        elif isinstance(event, TestFinished):
            if self._test is not None:
                self._test.finished = event
            self._test = None
        elif isinstance(event, ContentEvent):
            if self._test is not None:
                self._test.content.append(event)
            else:
                self._groups[-1].children.append(event)
        super().handle(event)

    def close(self) -> None:
        if not self._written:
            self._written = True
            self.write(self.run)

    def write(self, run: RunRecord) -> None:
        """Render the recorded run."""
        raise NotImplementedError
