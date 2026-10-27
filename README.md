# FixtureRig

**Python tests for physical systems.**

FixtureRig is an object-oriented test framework for hardware-in-the-loop (HIL) and other physical-system testing. You write tests and device fixtures as ordinary Python classes. The concrete rig (ports, addresses, limits, calibration values) goes in YAML files outside the code. The same test then runs on any bench by switching the config.

> **Status: early development (v0.1.0).** The core loop works: config parsing, inheritance-aware object construction, ordered execution, fixture lifecycle and multi-format reporting. Real device drivers (CAN, power supplies, ...), test generators and CLI parameter overrides are not implemented yet. Expect the config schema to change.

## Why FixtureRig?

- **Plain Python, no framework DSL.** Dependencies are constructor arguments with type hints. A test that needs a power supply asks for one in it's test function parameters.
- **Configuration-driven rigs.** YAML describes which fixtures exist and how they are set up. Tests never hard-code `COM4` or `192.168.0.10`.
- **Strict, actionable config errors.** Misspelled keys, unknown parameters and missing required values are reported, never silently ignored.
- **Ordered execution for shared hardware.** Tests run in config order. Fixtures are created once, shared, and driven through an explicit lifecycle.
- **Reports that help with debugging.** Tests report text, tables, charts and checks into one report stream. Console, JSON, HTML, PDF, PDF test spec, Excel and Allure modules all read from that stream.
- **Easy for AI agents to work with.** Clear class names, type hints, docstrings and config examples give coding agents such as Claude Code or Copilot what they need to generate and iterate on tests.

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/aweluxgit/FixtureRig.git
cd FixtureRig
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # dev extra includes Excel and PDF report support
```

Run the bundled demo. It uses a simulated device, so no hardware is needed:

```bash
cd demo/test_02
fixturerig --config config/env.yaml --config config/test.yaml
```

You should see something like:

```
  Ramping the supply to 4.5 V (limit 6.0 V)
  Chart: Voltage ramp (line)
  ...
  (passed) every reading matches its setpoint
  (passed) final voltage 4.50 V <= 6.0 V
[PASSED] sometest (0.053s)
=== 1 passed (1 test(s) in 0.05s) ===
```

The JSON, HTML, PDF, test spec PDF, Excel and Allure reports are written to `demo/reports/test_02/`.

## How it works

### 1. Write a test

```python
from fixturerig.base import TestCase
from fixturerig.fixtures.dummy_fixture import DummyFixture
from fixturerig.report import report


class TestCase01(TestCase):
    """Ramps the simulated supply voltage up to `volt` and checks it stays within `limit`."""

    def setup(self, dummy: DummyFixture) -> None:
        dummy.write("voltage", 0.0)

    def test(self, dummy: DummyFixture, volt: float, limit: float) -> bool:
        report.text(f"Ramping the supply to {volt} V")
        dummy.write("voltage", volt)
        reading = dummy.read("voltage")
        return report.check(reading <= limit, f"{reading:.2f} V <= {limit} V")

    def teardown(self, dummy: DummyFixture) -> None:
        dummy.write("voltage", 0.0)
```

FixtureRig fills the parameters of `__init__`, `setup`, `test` and `teardown` from the test's `parametermap`, matching by name. A parameter can appear in more than one method; above, `setup`, `test` and `teardown` all get the same `dummy` fixture. Type hints drive conversion. The `dummy: DummyFixture` type hint is all FixtureRig needs: any parameter annotated with a `Fixture` subclass is resolved by name to a configured fixture.

### 2. Describe the rig and the tests in YAML

```yaml
# config/env.yaml: the rig
- pythonpath: ..                      # make the project's own modules importable

- fixture:
    name: dummy
    class: fixturerig.fixtures.dummy_fixture.DummyFixture

- report:
    class: fixturerig.report.html.HtmlReport
    parameterpath:
      path: ../reports/report.html    # relative to this file
    parametermap:
      title: "My bench"
```

```yaml
# config/test.yaml: what to run
- testcase:
    name: voltage_ramp
    class: tests.testcase_01.TestCase01
    traceability: REQ-1234
    parametermap:
      dummy: dummy                    # reference to the fixture above
      volt: 4.5
      limit: 6.0

- testgroup:
    name: regression
    entries:
      - testcase:
          name: another_test
          class: tests.other.AnotherTest
```

Config files given with repeated `--config` options are merged in order. Splitting the rig description from the test selection lets you reuse one with the other.

### 3. Run

```bash
fixturerig --config config/env.yaml --config config/test.yaml
```

The exit code is `0` when the run completes, `1` for a configuration error and `2` for an invalid argument.

## Core concepts

### Fixtures

A fixture wraps a device or interface. Subclass `fixturerig.base.Fixture` and override only the hooks you need:

| Hook          | When it runs                                                          |
|---------------|-----------------------------------------------------------------------|
| `setup`       | Once, when a test first needs the fixture. Connect here.              |
| `self_test`   | Right after `setup`. Return `False` and dependent tests are skipped.  |
| `start`       | Before each test that uses the fixture.                               |
| `stop`        | After each test that used the fixture.                                |
| `lazy_stop`   | When the next test no longer needs a fixture the previous one used.   |
| `disconnect`  | After the last test, before teardown. Detach safely.                  |
| `teardown`    | After the last test. Release resources.                               |

Fixtures are created lazily and shared by every test that references them. They are torn down in reverse creation order. A fixture that fails setup or its self test is marked broken, and later tests that need it are skipped instead of retrying the hardware.

### Test cases

Subclass `fixturerig.base.TestCase` and implement `test()`. `setup()` and `teardown()` are optional. Config parameters are passed by name to whichever of `__init__`, `setup()`, `test()` and `teardown()` declare them, so several methods can receive the same value. A parameter that no method declares, or a required parameter that is missing, skips the test. Fixtures get their parameters through `__init__` only. The verdict is decided as follows:

| Outcome                                              | Verdict   |
|------------------------------------------------------|-----------|
| `test()` returns `True` / `False`                    | passed / failed |
| `test()` returns a `Verdict`                         | that verdict |
| `test()` raises a `VerdictException`                 | its verdict |
| `test()` raises any other exception                  | error     |
| `test()` returns nothing                             | none (counted as not passed) |
| Class can't be loaded, bad params, broken fixture    | skipped   |
| A `report.check(...)` failed during the test       | failed, even if `test()` returned `True` |

### Reporting

Tests and fixtures report through the global stream:

```python
from fixturerig.report import report

report.text("Ramping supply to 5 V")
report.table([["U", 4.93], ["I", 0.21]], headers=["Signal", "Value"])
report.chart("Ramp", {"U": (times, volts)}, x_label="s", y_label="V")
report.check(volts[-1] < 5.1, "final voltage below 5.1 V")
```

Every configured report module picks up the events it cares about. The console report is always on. The other modules are enabled with `report` entries:

| Module                                     | Output                      | Extra   |
|--------------------------------------------|-----------------------------|---------|
| `fixturerig.report.console.ConsoleReport`  | Console (default)           |         |
| `fixturerig.report.json_report.JsonReport` | JSON                        |         |
| `fixturerig.report.html.HtmlReport`        | Single HTML file            |         |
| `fixturerig.report.allure.AllureReport`    | Allure results directory    |         |
| `fixturerig.report.excel.ExcelReport`      | `.xlsx`                     | `excel` |
| `fixturerig.report.pdf.PdfReport`          | PDF report                  | `pdf`   |
| `fixturerig.report.pdf.PdfTestSpecReport`  | PDF test specification      | `pdf`   |

Install extras with `pip install -e ".[excel,pdf]"`. The test spec report ignores verdicts and builds a specification document from test docstrings, parameters and traceability IDs.

## Configuration reference (current subset)

Each config file is a YAML list. Each item is a single-key mapping:

| Entry        | Keys                                                                   |
|--------------|------------------------------------------------------------------------|
| `fixture`    | `name`, `class` (required); `parametermap`, `parameterpath`            |
| `testcase`   | `name`, `class` (required); `parametermap`, `parameterpath`, `traceability` |
| `testgroup`  | A list of entries, or `{name, entries}` for a named group              |
| `report`     | `class` (required); `name`, `parametermap`, `parameterpath`            |
| `pythonpath` | A path added to the import roots                                       |

- `class` is a Python import path (`package.module.Class`), resolved against the configured `pythonpath` roots.
- `parametermap` values are taken literally (scalars, lists, mappings).
- `parameterpath` values are paths, relative to the config file by default. A mapping with `path` and `base_path` or `base_module` sets a different base.
- Parameter names are matched to the class's constructor arguments, including inherited ones.

## Using FixtureRig as a library

The CLI is a thin wrapper. The same building blocks can be called from another test system:

```python
from pathlib import Path

from fixturerig.config.model import Config
from fixturerig.config.parse_yaml import read_config_files
from fixturerig.core.class_loader import add_python_paths
from fixturerig.core.runner import run_tests
from fixturerig.report.loader import build_report_stream

config = Config(entries=[])
read_config_files(config, [Path("config/env.yaml"), Path("config/test.yaml")])
add_python_paths(config)

stream = build_report_stream(config)
try:
    results = run_tests(config, stream)
finally:
    stream.close()

for r in results:
    print(r.name, r.verdict, f"{r.duration:.3f}s")
```

## Project layout

```
src/fixturerig/
  base/       Fixture, TestCase and Verdict base classes
  config/     YAML / CLI parsing and the config model
  core/       Class loading, inheritance-aware argument mapping, the runner
  fixtures/   Reusable fixtures (currently DummyFixture, a simulated device)
  report/     Report stream, report elements and report modules
  main.py     Command-line entry point
demo/         Example projects (start with demo/test_02)
tests/        pytest suite
```

## Roadmap

Planned, roughly in priority order:

- Device fixtures for power supplies, CAN, Ethernet and XIL, with replaceable drivers
- Test generators that create test cases from configuration or DUT information
- `--param` overrides with a defined precedence model
- Environment and device setup phases (time sync, flashing, DUT info gathering)
- A local web UI for device configuration, interactive tests and monitoring

## Development

A VS Code dev container is included (`.devcontainer/`). It creates `.venv` and installs the project with dev extras. To run the tests:

```bash
pytest
```

A `FixtureRig: demo test_02` launch configuration in `.vscode/launch.json` runs the demo under the debugger.

### Building a wheel

```bash
pip install build
python -m build                      # writes dist/fixturerig-<version>-py3-none-any.whl and the sdist
```

Install the wheel into any virtual environment. Activating that environment puts the `fixturerig` command on `PATH`. On Windows, pip creates `.venv\Scripts\fixturerig.exe` for it:

```bash
pip install dist/fixturerig-0.1.0-py3-none-any.whl          # core only
pip install "dist/fixturerig-0.1.0-py3-none-any.whl[all]"   # with Excel and PDF reports
fixturerig --version
python -m fixturerig --version      # equivalent, without the launcher
```

Other test systems can declare `fixturerig` (or `fixturerig[pdf]` etc.) as a normal dependency. The package ships a `py.typed` marker, so type checkers use its annotations.

## License

[MIT](LICENSE) © 2026 Alexander Werth
