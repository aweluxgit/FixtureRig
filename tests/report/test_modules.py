import io
import json
import struct
import zlib

import pytest

from fixturerig.base import Fixture
from fixturerig.base import TestCase as BaseTestCase  # aliased so pytest does not collect it
from fixturerig.config.model import Config
from fixturerig.config.model import Fixture as FixtureEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.config.model import TestGroup
from fixturerig.core.runner import run_tests
from fixturerig.report import ColoredConsoleReport, ConsoleReport, Image, ReportStream, Table, report
from fixturerig.report.allure import AllureReport
from fixturerig.report.html import HtmlReport
from fixturerig.report.json_report import JsonReport



def _png(width: int = 2, height: int = 2) -> bytes:
    """A small, valid RGB PNG."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\x20\x80\xc0" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


PNG = _png()


def cls_path(cls: type) -> str:
    return f"{__name__}.{cls.__name__}"


class Psu(Fixture):
    def setup(self):
        report.text("psu connected")


class Measures(BaseTestCase):
    """Ramps the supply and checks the final voltage."""

    def __init__(self, psu: Psu, limit: float):
        self.limit = limit

    def test(self):
        report.text("ramping <supply>")
        report.table([["U", 4.9], ["I", 0.2]], headers=["Signal", "Value"], title="Readings")
        report.table(Table([["nested", Table([["a", 1]])], ["picture", Image(data=PNG, caption="pic")]]))
        report.chart("Ramp", {"U": ([0, 1, 2], [0.0, 2.5, 4.9])}, x_label="s", y_label="V")
        report.chart("Bars", {"n": (["a", "b"], [1, 3])}, kind="bar")
        report.chart("Dots", {"n": ([0, 1], [1, 3])}, kind="scatter")
        report.image(Image(data=PNG, caption="scope"))
        report.check(True, "U within limit")
        return True


class FailsCheck(BaseTestCase):
    def test(self):
        report.check(False, "U above 5.1 V")
        return True


def make_config() -> Config:
    return Config(
        entries=[
            FixtureEntry(name="psu", cls=cls_path(Psu)),
            TestGroup(
                name="Power",
                entries=[
                    TestCaseEntry(
                        name="ramp",
                        cls=cls_path(Measures),
                        params={"psu": "psu", "limit": 5.0},
                        traceability=["REQ-1"],
                    ),
                    TestCaseEntry(name="overvoltage", cls=cls_path(FailsCheck)),
                ],
            ),
            TestCaseEntry(name="missing", cls=f"{__name__}.DoesNotExist"),
        ]
    )


def run_with(*modules) -> None:
    stream = ReportStream(modules)
    run_tests(make_config(), stream)
    stream.close()


# --- console -------------------------------------------------------------------


def test_console_report_prints_groups_tests_content_and_summary():
    out = io.StringIO()
    run_with(ConsoleReport(output=out))
    text = out.getvalue()

    assert "=== FixtureRig test run ===" in text
    assert "> Power" in text
    assert "- ramp" in text and "[REQ-1]" in text
    assert "ramping <supply>" in text
    assert "| U      | 4.9   |" in text
    assert "(passed) U within limit" in text
    assert "[PASSED] ramp" in text
    assert "[FAILED] overvoltage" in text
    assert "[SKIPPED] missing" in text
    assert "1 passed, 1 failed, 1 skipped (3 test(s)" in text


@pytest.mark.parametrize("verbosity, shown, hidden", [
    (0, ["1 passed"], ["[PASSED] ramp", "ramping"]),
    (1, ["[PASSED] ramp", "> Power"], ["ramping"]),
])
def test_console_verbosity(verbosity, shown, hidden):
    out = io.StringIO()
    run_with(ConsoleReport(verbosity=verbosity, output=out))
    for text in shown:
        assert text in out.getvalue()
    for text in hidden:
        assert text not in out.getvalue()


def test_colored_console_colors_only_when_forced_or_tty():
    plain, forced = io.StringIO(), io.StringIO()
    run_with(ColoredConsoleReport(output=plain), ColoredConsoleReport(output=forced, force_color=True, verbosity=1))

    assert "\033[" not in plain.getvalue()
    assert "\033[32m[PASSED]\033[0m ramp" in forced.getvalue()
    assert "ramping" not in forced.getvalue()  # verbosity is inherited from ConsoleReport


# --- json ----------------------------------------------------------------------


def test_json_report_writes_result_tree(tmp_path):
    path = tmp_path / "out" / "report.json"
    run_with(JsonReport(path=path))
    data = json.loads(path.read_text())

    assert data["counts"] == {"passed": 1, "failed": 1, "skipped": 1}
    group, missing = data["items"]
    assert group["type"] == "group" and group["name"] == "Power"
    ramp, overvoltage = group["items"]
    assert ramp["path"] == ["Power", "ramp"]
    assert ramp["description"] == "Ramps the supply and checks the final voltage."
    assert ramp["params"] == {"psu": "psu", "limit": 5.0}
    assert ramp["traceability"] == ["REQ-1"]
    assert ramp["verdict"] == {"status": "passed", "message": ""}
    # The fixture is created while the test resolves its arguments, so the
    # fixture's setup() output is part of the test that first needed it.
    assert ramp["content"][0]["text"]["text"] == "psu connected"
    assert [c["event"] for c in ramp["content"][1:]] == [
        "text", "table", "table", "chart", "chart", "chart", "image", "verdict",
    ]
    assert ramp["content"][3]["table"]["rows"][0][1]["type"] == "table"
    assert overvoltage["verdict"]["status"] == "failed"
    assert "U above 5.1 V" in overvoltage["verdict"]["message"]
    assert missing["verdict"]["status"] == "skipped"


def test_json_report_records_content_outside_tests(tmp_path):
    path = tmp_path / "report.json"
    stream = ReportStream([JsonReport(path=path)])
    stream.text("rig notes")
    stream.close()
    assert json.loads(path.read_text())["items"] == [
        {**json.loads(path.read_text())["items"][0], "event": "text", "test": None}
    ]


# --- html ----------------------------------------------------------------------


def test_html_report_is_self_contained_and_escaped(tmp_path):
    path = tmp_path / "report.html"
    run_with(HtmlReport(path=path, title="Rig 7"))
    html = path.read_text()

    assert html.startswith("<!doctype html>")
    assert "<title>Rig 7</title>" in html
    assert "ramping &lt;supply&gt;" in html
    assert "<caption>Readings</caption>" in html
    assert html.count("<svg") == 3
    assert "<polyline" in html and "<rect" in html
    assert "data:image/png;base64," in html
    assert 'class="badge s-failed"' in html
    assert "REQ-1" in html
    assert "<table><tr><td>nested</td><td><table>" in html  # complex table renders natively


# --- allure --------------------------------------------------------------------


def test_allure_report_writes_results_and_attachments(tmp_path):
    results = tmp_path / "allure-results"
    run_with(AllureReport(results_dir=results, tms_url="https://tms.example/browse/{}"))

    loaded = [json.loads(p.read_text()) for p in results.glob("*-result.json")]
    by_name = {r["name"]: r for r in loaded}
    assert set(by_name) == {"ramp", "overvoltage", "missing"}

    ramp = by_name["ramp"]
    assert ramp["status"] == "passed"
    assert ramp["fullName"] == "Power.ramp"
    assert {"name": "suite", "value": "Power"} not in ramp["labels"]
    assert {"name": "parentSuite", "value": "Power"} in ramp["labels"]
    assert ramp["links"] == [{"name": "REQ-1", "type": "tms", "url": "https://tms.example/browse/REQ-1"}]
    assert ramp["steps"][0]["name"] == "U within limit"
    types = sorted(a["type"] for a in ramp["attachments"])
    assert types == sorted(
        ["text/plain", "text/csv", "text/plain", "application/json", "application/json",
         "application/json", "image/png", "text/plain"]
    )
    for attachment in ramp["attachments"]:
        assert (results / attachment["source"]).exists()

    assert by_name["overvoltage"]["status"] == "failed"
    assert by_name["missing"]["status"] == "skipped"


def test_allure_clean_removes_previous_results(tmp_path):
    results = tmp_path / "allure-results"
    results.mkdir()
    (results / "old-result.json").write_text("{}")
    run_with(AllureReport(results_dir=results, clean=True))
    assert not (results / "old-result.json").exists()


# --- excel / pdf (optional dependencies) ---------------------------------------


def test_excel_report_writes_summary_details_and_charts(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from fixturerig.report.excel import ExcelReport

    path = tmp_path / "report.xlsx"
    run_with(ExcelReport(path=path))
    workbook = openpyxl.load_workbook(path)

    assert workbook.sheetnames == ["Summary", "Details", "Charts"]
    summary = [[c.value for c in row] for row in workbook["Summary"].iter_rows(min_row=2)]
    assert [row[1:3] for row in summary] == [["ramp", "passed"], ["overvoltage", "failed"], ["missing", "skipped"]]
    assert summary[0][0] == "Power" and summary[0][6] == "REQ-1"
    details = [[c.value for c in row] for row in workbook["Details"].iter_rows(min_row=2)]
    assert [None, None, "U", 4.9] in details
    assert len(workbook["Charts"]._charts) == 3


def test_pdf_reports_are_written(tmp_path):
    pytest.importorskip("reportlab")
    from fixturerig.report.pdf import PdfReport, PdfTestSpecReport

    report_path, spec_path = tmp_path / "report.pdf", tmp_path / "spec.pdf"
    spec = PdfTestSpecReport(path=spec_path)
    run_with(PdfReport(path=report_path), spec)

    assert report_path.read_bytes().startswith(b"%PDF")
    assert spec_path.read_bytes().startswith(b"%PDF")
    # The spec report never sees verdicts or test content.
    recorded = spec.run.tests()
    assert [t.name for t in recorded] == ["ramp", "overvoltage", "missing"]
    assert all(t.finished is None and t.content == [] for t in recorded)
    assert spec.run.finished is not None


def test_pdf_report_survives_a_broken_image(tmp_path):
    pytest.importorskip("reportlab")
    from fixturerig.report.pdf import PdfReport

    path = tmp_path / "report.pdf"
    stream = ReportStream([PdfReport(path=path)])
    stream.image(Image(data=b"not a png", caption="broken"))
    stream.close()

    assert path.read_bytes().startswith(b"%PDF")


def test_spec_filter_ignores_verdicts():
    pytest.importorskip("reportlab")
    from fixturerig.report import TestFinished, VerdictEvent
    from fixturerig.base import Verdict
    from fixturerig.report.pdf import PdfTestSpecReport

    spec = PdfTestSpecReport()
    assert not spec.accepts(TestFinished(name="t"))
    assert not spec.accepts(VerdictEvent(Verdict(True)))
