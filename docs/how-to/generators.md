# Generate tests from data

A **generator** creates test entries at run time, for example one test per voltage in a sweep, or one per row in a requirements spreadsheet.

## Write a generator

Subclass {class}`fixturerig.base.Generator` and implement `generate()`. It returns config entries built from {mod}`fixturerig.config.model`: {class}`~fixturerig.config.model.TestCase`, {class}`~fixturerig.config.model.TestGroup` or another {class}`~fixturerig.config.model.Generator`.

```python
from fixturerig.base import Generator
from fixturerig.config.model import TestCase


class VoltageSweep(Generator):
    """One VoltageLimit test per voltage."""

    def generate(self, voltages: list[float]):
        return [
            TestCase(name=f"voltage_{v}", cls="project.tests.VoltageLimit", params={"limit": v})
            for v in voltages
        ]
```

```yaml
- generator:
    name: voltage_sweep
    class: project.generators.VoltageSweep
    parametermap:
      voltages: [3.3, 4.5, 5.0]
```

This produces a group `voltage_sweep` containing `voltage_3.3`, `voltage_4.5` and `voltage_5.0`, inserted where the generator is declared.

## Options

`create_group` (default `true`)
: Wraps the generated entries in a test group named after the generator. Set it to `false` to insert them directly.

`name` (required)
: Names the generator and its group. It is required so generators from different config files can be merged.

Parameters are passed to `__init__` and `generate()`, like a test's.

## Limits

- Generators run first, before `env_setup` and `dut_info`. They can't use DUT information and can't take fixture parameters.
- Generated entries can be test cases, groups or generators. Nested generators are expanded too. Generators can't create lifecycle steps.
- Any problem while generating (unknown class, bad parameters, an exception, an invalid return value) stops the run with a config error, before any hardware is touched.
