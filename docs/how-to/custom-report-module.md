# Write a report module

A report module is a subclass of {class}`fixturerig.report.ReportModule`. It is attached to the run's report stream and receives every event it accepts.

```python
from pathlib import Path

from fixturerig.report import ReportModule, TestFinished


class CsvSummary(ReportModule):
    """Writes one CSV line per test: name, verdict, duration."""

    event_kinds = frozenset({"test_finished"})

    def __init__(self, path: Path, **kwargs):
        super().__init__(**kwargs)          # receives e.g. `exclude`
        self.path = path
        self.rows: list[str] = []

    def on_test_finished(self, event: TestFinished) -> None:
        self.rows.append(f"{event.name},{event.verdict.status.value},{event.duration:.3f}")

    def close(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("name,verdict,duration\n" + "\n".join(self.rows) + "\n")
```

```yaml
- report:
    class: project.reports.CsvSummary
    parameterpath:
      path: ../reports/summary.csv
```

## How events reach a module

1. {meth}`~fixturerig.report.ReportModule.accepts` decides whether the module wants an event. By default it accepts the kinds in the class attribute `event_kinds` (`None` means all) minus those in the `exclude` parameter. Override it for a different rule.
2. {meth}`~fixturerig.report.ReportModule.handle` calls `on_<kind>` (for example `on_text`, `on_test_finished`), or `on_event` when there is no such method.
3. {meth}`~fixturerig.report.ReportModule.close` is called once after the run. File-based modules write their output here. It must also work after an aborted run.

The event classes are listed in {mod}`fixturerig.report.events`.

## Build on a recording

Most file reports need the whole run before they can write anything. {class}`~fixturerig.report.RecordingReport` collects the events into a tree of groups and tests and calls `write(run)` once at the end. The JSON, HTML, Allure, Excel and PDF modules are built this way, so they make good examples.

## Configuration

Report modules are configured like fixtures: `parametermap` and `parameterpath` are mapped onto `__init__`, including parameters inherited through `**kwargs`. Report modules have no access to fixtures; a fixture-typed parameter is a config error. Any problem creating a module is reported as a config error before any test runs.
