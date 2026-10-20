#
# This module holds the Allure report module
#
# Design decisions:
# - Writes the standard Allure results directory (one `<uuid>-result.json`
#   per test plus attachment files), to be rendered with `allure serve` or
#   `allure generate`. No Allure Python package is needed.
# - Verdict mapping: passed -> passed, failed -> failed, error/none -> broken,
#   skipped -> skipped, knownfailed -> skipped (like pytest's xfail).
# - Test group names become Allure suite labels (parentSuite / suite /
#   subSuite for the first three levels).
# - Traceability IDs become "tms" links. With `tms_url` (e.g.
#   "https://jira.example.com/browse/{}") they link to the tool.
# - Reported verdicts become steps, reported content becomes attachments:
#   text -> text/plain, table -> text/csv (simple) or text/plain (complex),
#   chart -> application/json, image -> its file.
#

from __future__ import annotations

import csv
import io
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fixturerig.base.verdict import VerdictStatus
from fixturerig.report.elements import Chart, Image, Table, Text
from fixturerig.report.events import ContentEvent, VerdictEvent
from fixturerig.report.recording import RecordingReport, RunRecord, TestRecord

_STATUS = {
    VerdictStatus.PASSED: "passed",
    VerdictStatus.FAILED: "failed",
    VerdictStatus.ERROR: "broken",
    VerdictStatus.NONE: "broken",
    VerdictStatus.SKIPPED: "skipped",
    VerdictStatus.KNOWNFAILED: "skipped",
}
_SUITE_LABELS = ("parentSuite", "suite", "subSuite")
_IMAGE_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/svg+xml": "svg"}


class AllureReport(RecordingReport):
    """Writes Allure result files for every test.

    :param results_dir: the Allure results directory.
    :param clean: delete existing results in `results_dir` before writing.
    :param tms_url: URL pattern for traceability links; ``{}`` is replaced by the ID.
    """

    def __init__(
        self,
        results_dir: Path = Path("allure-results"),
        clean: bool = False,
        tms_url: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.results_dir = Path(results_dir)
        self.clean = clean
        self.tms_url = tms_url

    def write(self, run: RunRecord) -> None:
        if self.clean and self.results_dir.exists():
            shutil.rmtree(self.results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        for test in run.tests():
            self._write_test(test)

    def _write_test(self, test: TestRecord) -> None:
        spec = test.started
        done = test.finished
        start = _ms(spec.timestamp)
        stop = _ms(done.timestamp) if done else start
        status = _STATUS[done.verdict.status] if done else "unknown"
        groups = list(spec.path[:-1])
        full_name = ".".join([*groups, spec.name])

        labels = [{"name": "testClass", "value": spec.cls}, {"name": "framework", "value": "fixturerig"}]
        labels += [{"name": label, "value": group} for label, group in zip(_SUITE_LABELS, groups)]
        if done and done.verdict.status is VerdictStatus.KNOWNFAILED:
            labels.append({"name": "tag", "value": "knownfailed"})

        steps = []
        attachments = []
        for event in test.content:
            if isinstance(event, VerdictEvent):
                steps.append(
                    {
                        "name": event.verdict.message or event.verdict.status.value,
                        "status": _STATUS[event.verdict.status],
                        "stage": "finished",
                        "start": _ms(event.timestamp),
                        "stop": _ms(event.timestamp),
                    }
                )
            else:
                attachment = self._write_attachment(event)
                if attachment is not None:
                    attachments.append(attachment)

        result: dict[str, Any] = {
            "uuid": str(uuid.uuid4()),
            "historyId": full_name,
            "testCaseId": full_name,
            "name": spec.name,
            "fullName": full_name,
            "description": spec.description,
            "status": status,
            "statusDetails": {"message": done.verdict.message if done else "test did not finish"},
            "stage": "finished",
            "start": start,
            "stop": stop,
            "labels": labels,
            "links": [self._link(ref) for ref in spec.traceability],
            "parameters": [{"name": name, "value": str(value)} for name, value in spec.params.items()],
            "steps": steps,
            "attachments": attachments,
        }
        path = self.results_dir / f"{result['uuid']}-result.json"
        path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    def _link(self, ref: str) -> dict[str, str]:
        link = {"name": ref, "type": "tms"}
        if self.tms_url:
            link["url"] = self.tms_url.replace("{}", ref)
        return link

    def _write_attachment(self, event: ContentEvent) -> dict[str, str] | None:
        element = event.element
        if isinstance(element, Text):
            return self._attach("Text", element.text.encode("utf-8"), "text/plain", "txt")
        if isinstance(element, Table):
            name = element.title or "Table"
            if element.is_simple:
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                if element.headers:
                    writer.writerow(element.headers)
                writer.writerows(element.text_rows())
                return self._attach(name, buffer.getvalue().encode("utf-8"), "text/csv", "csv")
            return self._attach(name, element.to_text().encode("utf-8"), "text/plain", "txt")
        if isinstance(element, Chart):
            data = json.dumps(element.to_dict(), indent=2, default=str).encode("utf-8")
            return self._attach(element.title or "Chart", data, "application/json", "json")
        if isinstance(element, Image):
            extension = _IMAGE_EXTENSIONS.get(element.mime_type, "bin")
            return self._attach(element.caption or "Image", element.read_bytes(), element.mime_type, extension)
        return None

    def _attach(self, name: str, data: bytes, mime_type: str, extension: str) -> dict[str, str]:
        source = f"{uuid.uuid4()}-attachment.{extension}"
        (self.results_dir / source).write_bytes(data)
        return {"name": name, "source": source, "type": mime_type}


def _ms(timestamp: float) -> int:
    return int(timestamp * 1000)
