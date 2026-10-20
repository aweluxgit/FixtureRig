#
# This module holds the base class for report modules
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Reporting"):
#
# - A report module is attached to a ReportStream and receives every event
#   it `accepts()`. The default filter is the class attribute `event_kinds`
#   (None = every kind) minus the kinds given in the `exclude` config
#   parameter. A module that needs a different rule overrides accepts().
#
# - handle() dispatches to an `on_<kind>` method (on_text, on_test_finished,
#   ...), falling back to on_event(). Modules implement only the handlers
#   they need.
#
# - close() is called once after the run, so file based modules write their
#   output there. It must be safe to call even if the run was aborted early.
#
# - Report modules are configured exactly like fixtures and testcases: the
#   `parametermap` of a `report` entry is mapped onto __init__ with
#   fixturerig.core.inheritance, so a subclass may take its own parameters
#   and forward the rest with **kwargs:
#
#       class MyReport(ReportModule):
#           def __init__(self, path: Path, **kwargs):
#               super().__init__(**kwargs)   # receives e.g. `exclude`
#               self.path = path
#

from __future__ import annotations

from typing import ClassVar

from fixturerig.report.events import EVENT_KINDS, ReportEvent


class ReportModule:
    """Base class for report modules attached to a report stream.

    :param exclude: event kinds this module ignores, e.g. ``["text", "chart"]``.
    """

    event_kinds: ClassVar[frozenset[str] | None] = None

    def __init__(self, exclude: list[str] | None = None):
        unknown = sorted(set(exclude or ()) - EVENT_KINDS)
        if unknown:
            raise ValueError(
                f"Unknown event kind(s) {unknown} in exclude; known: {sorted(EVENT_KINDS)}"
            )
        self.exclude = frozenset(exclude or ())

    def accepts(self, event: ReportEvent) -> bool:
        """Whether this module wants to receive `event`."""
        if event.kind in self.exclude:
            return False
        return self.event_kinds is None or event.kind in self.event_kinds

    def handle(self, event: ReportEvent) -> None:
        """Dispatch an accepted event to its ``on_<kind>`` handler."""
        handler = getattr(self, f"on_{event.kind}", None)
        if handler is None:
            self.on_event(event)
        else:
            handler(event)

    def on_event(self, event: ReportEvent) -> None:
        """Fallback for event kinds without a dedicated handler."""

    def close(self) -> None:
        """Finish the report, e.g. write it to disk. Called once after the run."""
