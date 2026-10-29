# Write a test case

Subclass {class}`fixturerig.base.TestCase` and implement `test()`. `setup()` and `teardown()` are optional.

```python
from fixturerig.base import TestCase, Verdict, VerdictStatus
from fixturerig.report import report

from project.fixtures import PowerSupply


class VoltageLimit(TestCase):
    """Sets the supply to half the limit and checks the measured voltage."""

    def __init__(self, tolerance: float = 0.05):
        self.tolerance = tolerance

    def setup(self, power_supply: PowerSupply) -> None:
        power_supply.output(False)

    def test(self, power_supply: PowerSupply, limit: float) -> bool:
        power_supply.set_voltage(limit / 2)
        measured = power_supply.measure_voltage()
        return report.check(abs(measured - limit / 2) <= self.tolerance, f"measured {measured:.3f} V")

    def teardown(self, power_supply: PowerSupply) -> None:
        power_supply.output(False)
```

```yaml
- testcase:
    name: voltage_limit
    class: project.tests.VoltageLimit
    traceability: [REQ-12, REQ-13]
    parametermap:
      limit: 4.5
      tolerance: 0.02
```

## How parameters reach the methods

Every key in `parametermap` and `parameterpath` is passed by name to whichever of `__init__`, `setup`, `test` and `teardown` declare it. Several methods may take the same key. A key that no method declares is an error, and so is a required parameter that the config doesn't provide. In both cases the test is skipped with a message naming the parameter.

Type hints control how values are converted. See {doc}`../explanation/argument-mapping`.

## Use fixtures

A parameter whose type hint is a {class}`~fixturerig.base.Fixture` subclass is a reference to a configured fixture, not a value:

- If the config doesn't mention the parameter, it gets the fixture with the **same name**.
- If the names differ, map them with `fixturemap`:

  ```yaml
  - testcase:
      name: voltage_limit
      class: project.tests.VoltageLimit
      fixturemap:
        power_supply: psu_bench_2     # test parameter: configured fixture name
  ```

A parameter with a default value keeps its default unless you name it in the `fixturemap`.

## Decide the verdict

| Outcome                                         | Verdict                                   |
|-------------------------------------------------|-------------------------------------------|
| `test()` returns `True` / `False`               | passed / failed                           |
| `test()` returns a {class}`~fixturerig.base.Verdict` | that verdict                         |
| `test()` raises a {class}`~fixturerig.base.VerdictException` | its verdict                  |
| `test()` or `setup()` raises any other exception | error                                    |
| `teardown()` or a fixture's `start`/`stop` raises | error, unless the verdict is already worse |
| `test()` returns nothing                        | none (counted as not passed)              |
| A `report.check()` failed during the test       | failed, even if `test()` returned `True`  |
| Class can't be loaded, bad parameters, broken fixture | skipped                             |

A test may return or raise only `passed`, `failed` or `skipped`. The other statuses are reserved for the runner. To stop a test early with a specific verdict, raise a {class}`~fixturerig.base.VerdictException`:

```python
from fixturerig.base import Verdict, VerdictException, VerdictStatus

if not power_supply.is_calibrated():
    raise VerdictException(Verdict(VerdictStatus.SKIPPED, "supply not calibrated"))
```

## Record several checks

`report.check(condition, message)` records a passed or failed check and returns the condition. One failed check fails the test, so a test can record many checks and still `return True` at the end:

```python
def test(self, dut: Dut) -> bool:
    report.check(dut.read_id() == 0x42, "device ID")
    report.check(dut.read_temperature() < 85, "temperature in range")
    return True
```

## Group tests

```yaml
- testgroup:
    name: regression
    entries:
      - testcase: {name: t1, class: project.tests.T1}
      - testcase: {name: t2, class: project.tests.T2}
```

Groups can be nested. A group without a name can be written as a plain list: `- testgroup: [ ... ]`.

## Document the test

The class docstring is the test's description. It appears in the reports and in the PDF test specification, together with the parameters and `traceability` IDs. Write it as the test specification: what the test does and what it expects.
