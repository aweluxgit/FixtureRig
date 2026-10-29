# Report results

Tests, fixtures, steps and generators report through one global stream, `report`:

```python
from fixturerig.report import report

report.text("Ramping supply to 5 V")
report.table([["U", 4.93], ["I", 0.21]], headers=["Signal", "Value"], title="Readings")
report.chart("Ramp", {"U": (times, volts)}, x_label="s", y_label="V")
report.image("scope_capture.png", caption="Ripple at 5 V")
report.check(volts[-1] < 5.1, "final voltage below 5.1 V")
```

| Call | Reports |
|------|---------|
| {meth}`~fixturerig.report.ReportStream.text` | A block of text |
| {meth}`~fixturerig.report.ReportStream.table` | A table, from rows of cells or a {class}`~fixturerig.report.elements.Table`. Cells may be other elements, including tables. |
| {meth}`~fixturerig.report.ReportStream.chart` | A chart, from a title and `{name: (x_values, y_values)}`, or a {class}`~fixturerig.report.elements.Chart` |
| {meth}`~fixturerig.report.ReportStream.image` | An image file, or an {class}`~fixturerig.report.elements.Image` |
| {meth}`~fixturerig.report.ReportStream.check` | A passed or failed check; returns the condition |
| {meth}`~fixturerig.report.ReportStream.verdict`, `passed`, `failed` | An intermediate verdict |

A failed check or verdict makes the test fail, even if `test()` returns `True`.

## Enable report modules

Every configured report module receives the events it cares about. The console report is always on; the others are enabled with `report` entries:

```yaml
- report:
    class: fixturerig.report.html.HtmlReport
    parameterpath:
      path: ../reports/report.html
    parametermap:
      title: "Bench 2 nightly"
```

| Module | Output | Parameters |
|--------|--------|------------|
| {class}`fixturerig.report.console.ConsoleReport` | Console, on by default | `verbosity` (0–2) |
| {class}`fixturerig.report.console.ColoredConsoleReport` | Console with ANSI colours | `verbosity`, `force_color` |
| {class}`fixturerig.report.json_report.JsonReport` | JSON file | `path`, `indent` |
| {class}`fixturerig.report.html.HtmlReport` | Single, self-contained HTML file | `path`, `title` |
| {class}`fixturerig.report.allure.AllureReport` | Allure results directory | `results_dir`, `clean`, `tms_url` |
| {class}`fixturerig.report.excel.ExcelReport` | `.xlsx` workbook | `path` |
| {class}`fixturerig.report.pdf.PdfReport` | PDF report | `path`, `title` |
| {class}`fixturerig.report.pdf.PdfTestSpecReport` | PDF test specification | `path`, `title` |

Every module also takes `exclude`, a list of event kinds to ignore, for example `exclude: [text, chart]`.

```{tip}
Give output paths in `parameterpath`, not `parametermap`. Paths in `parameterpath` are resolved relative to the config file, so the report lands in the same place whatever directory you start the run from.
```

## Make the console quieter

Configuring a console report replaces the default one:

```yaml
- report:
    class: fixturerig.report.console.ConsoleReport
    parametermap:
      verbosity: 1     # 0 = summary only, 1 = + groups and verdicts, 2 = + everything tests report
```

## The test specification

{class}`~fixturerig.report.pdf.PdfTestSpecReport` ignores verdicts. It builds a specification document from each test's class docstring, parameters and `traceability` IDs, so you can produce a test spec from the same config that runs the tests.

To write your own module, see {doc}`custom-report-module`.
