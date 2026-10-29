# Your first project

This tutorial builds a small FixtureRig project from scratch. It uses the simulated {class}`~fixturerig.fixtures.dummy_fixture.DummyFixture`, so you need no hardware.

By the end you will have a test that ramps a simulated supply voltage, checks it against a limit from the config and writes an HTML report.

## 1. Lay out the project

```text
my_rig/
  config/
    env.yaml        # the rig: fixtures and reports
    test.yaml       # what to run
  tests/
    __init__.py     # empty
    voltage.py
```

Splitting the rig from the test selection lets you combine the same tests with different benches, or the same bench with different test sets.

## 2. Write the test

```python
# tests/voltage.py
from fixturerig.base import TestCase
from fixturerig.fixtures.dummy_fixture import DummyFixture
from fixturerig.report import report


class VoltageRamp(TestCase):
    """Ramps the simulated supply up to `volt` and checks it stays within `limit`."""

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

Things to notice:

- The test asks for its fixture by declaring a parameter `dummy: DummyFixture`. The type hint tells FixtureRig that `dummy` is a configured fixture, not a plain value.
- `volt` and `limit` come from the config. Their type hints control conversion.
- The same parameter can appear in several methods. `setup`, `test` and `teardown` all get the same `dummy` instance.
- `report.check` records a passed or failed check in the report and returns the condition, so it can be the test's return value.
- The class docstring is the test's description. The PDF test specification report prints it.

## 3. Describe the rig

```yaml
# config/env.yaml
- pythonpath: ..                      # makes the `tests` package importable

- fixture:
    name: dummy
    class: fixturerig.fixtures.dummy_fixture.DummyFixture

- report:
    class: fixturerig.report.html.HtmlReport
    parameterpath:
      path: ../reports/report.html    # relative to this file
    parametermap:
      title: "My first rig"
```

`pythonpath` is resolved relative to the config file, so `..` is the `my_rig` folder. Paths under `parameterpath` are also relative to the config file, so the report lands in `my_rig/reports/` wherever you start the run from.

## 4. Select the tests

```yaml
# config/test.yaml
- testcase:
    name: voltage_ramp
    class: tests.voltage.VoltageRamp
    traceability: REQ-1234
    parametermap:
      volt: 4.5
      limit: 6.0
```

The test's `dummy` parameter isn't mentioned here: a required fixture parameter that the config doesn't name gets the fixture with the same name.

## 5. Run it

```bash
cd my_rig
fixturerig --config config/env.yaml --config config/test.yaml
```

```text
=== FixtureRig test run ===
- voltage_ramp (tests.voltage.VoltageRamp) [REQ-1234]
  Ramping the supply to 4.5 V
  (passed) 4.50 V <= 6.0 V
[PASSED] voltage_ramp (0.030s)
=== 1 passed (1 test(s) in 0.03s) ===
```

FixtureRig's own log lines (`INFO fixturerig: ...`) go to stderr between these lines.

Open `reports/report.html` to see the same run as a web page.

## 6. Try a failure

Change `limit` to `4.0` in `test.yaml` and run again. The check fails and so does the test. Then misspell `volt` as `volts`. FixtureRig doesn't silently ignore the typo; it skips the test with a clear reason:

```text
[SKIPPED] voltage_ramp (0.032s): Missing required parameter: 'volt' for VoltageRamp.test
```

## Where next

- The bundled demo in `demo/test_02` shows charts, tables and every report module. Run it with `fixturerig --config config/env.yaml --config config/test.yaml` from that folder.
- {doc}`../how-to/write-a-fixture` shows how to wrap a real device.
- {doc}`../reference/config` lists every config key.
