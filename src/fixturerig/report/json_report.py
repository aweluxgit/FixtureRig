#
# This module holds the JSON report module
#
# Design decision: the JSON report is the machine readable result model for
# external systems (see high-level-design's "FixtureRig can return generated
# test identities and results"). It writes the run as a tree:
#
#   {"title", "started", "finished", "duration", "counts",
#    "items": [ {"type": "group", "name", "items": [...]},
#               {"type": "test", "name", "class", "description", "params",
#                "traceability", "verdict": {"status", "message"},
#                "duration", "content": [<event dicts>]},
#               <content event dicts reported outside any test> ]}
#
# Values JSON cannot represent (e.g. Path params) are written as strings.
#

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fixturerig.report.events import ContentEvent
from fixturerig.report.recording import GroupRecord, RecordingReport, RunRecord, TestRecord


class JsonReport(RecordingReport):
    """Writes the run's results and reported content to a JSON file.

    :param path: the file to write.
    :param indent: JSON indentation; 0 writes a compact file.
    """

    def __init__(self, path: Path = Path("fixturerig-report.json"), indent: int = 2, **kwargs):
        super().__init__(**kwargs)
        self.path = Path(path)
        self.indent = indent

    def write(self, run: RunRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as stream:
            json.dump(run_to_dict(run), stream, indent=self.indent or None, default=str)
            stream.write("\n")


def run_to_dict(run: RunRecord) -> dict[str, Any]:
    return {
        "title": run.title,
        "started": run.started.timestamp if run.started else None,
        "finished": run.finished.timestamp if run.finished else None,
        "duration": run.finished.duration if run.finished else None,
        "counts": run.counts(),
        "items": [_item_to_dict(child) for child in run.root.children],
    }


def _item_to_dict(item: GroupRecord | TestRecord | ContentEvent) -> dict[str, Any]:
    if isinstance(item, GroupRecord):
        return {
            "type": "group",
            "name": item.name,
            "duration": item.finished.duration if item.finished else None,
            "items": [_item_to_dict(child) for child in item.children],
        }
    if isinstance(item, TestRecord):
        spec = item.started
        done = item.finished
        return {
            "type": "test",
            "name": spec.name,
            "path": list(spec.path),
            "class": spec.cls,
            "description": spec.description,
            "params": spec.params,
            "traceability": spec.traceability,
            "started": spec.timestamp,
            "verdict": (
                {"status": done.verdict.status.value, "message": done.verdict.message} if done else None
            ),
            "duration": done.duration if done else None,
            "content": [event.to_dict() for event in item.content],
        }
    return item.to_dict()
