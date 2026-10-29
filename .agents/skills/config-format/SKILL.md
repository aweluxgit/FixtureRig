---
name: config-format
description: Detailed descriptions of the config format with examples.
---

## Format

Config files are in yaml format and parsed into an internal config model.


Available options in the config files:
- fixture
- testcase
- testgroup
- generator
- report
- plugin
- pythonpath
- parameters
- env_setup
- dut_info
- dut_shutdown


Common subfields for fixture, testcase, generator, report, and plugin entries:
- name
- class
- parametermap
- parameterlist
- parameterpath

The entries are run in order:
- generator
- env_setup
- dut_info
- testcase
- dut_shutdown


## Fields for parameterpath

The keys for all parameterpath entries are the parameter names.
The value can either be a string or a dictionary.
If it's a string it will be treated as if it's a dictionary with just the path entry.
Otherwise the dictionary can have these entries:
- path
    absolute path, relative path or uri
    if relative and no other base specified then it's relative to the config file
- base_module
    if it exists the path is relative to the directory of this module
- base_path
    if it exists the path is relative to this path

If the value for a parampath is a string and not a dict then it's a shorthand for the path field of the parampath entry.

## fixturemap

A testcase can have a `fixturemap` entry. Its keys are parameter names of the test, its values are the names of configured fixtures.
A required test parameter with a Fixture type hint that isn't named in the config is resolved to the fixture with the same name, so a fixturemap is only needed when the names differ.

```yaml
- fixture:
    name: psu_bench_2
    class: project.fixtures.Psu
- testcase:
    name: voltage_limit
    class: project.tests.VoltageLimitTest   # def test(self, power_supply: Psu, limit: float)
    fixturemap:
      power_supply: psu_bench_2
    parametermap:
      limit: 4.5
```

Every fixturemap key must match a parameter with a Fixture type hint, and may not also appear in parametermap or parameterpath.

## autoloaded

A fixture can have an `autoloaded` entry (`true` or `false`, default `false`).
Autoloaded fixtures are created right at the start of the run, even before the env_setup entries are run.
After that they behave as if every test required them under their configured name: they are started and stopped for each test.
A test can still require an autoloaded fixture explicitly to get a reference to it.

```yaml
- fixture:
    name: rbs
    class: project.fixtures.RestBusSimulation
    autoloaded: true
```

## generator

A generator entry configures a test generator class (a subclass of `fixturerig.base.Generator`).
It accepts `name` and `class` (required), `parametermap`, `parameterpath` and `create_group` (`true` or `false`, default `true`).
The name is required so generators from different config files can be merged.
The parameters are passed to the generator's `__init__` and `generate()` methods, like a testcase's parameters are passed to its methods.

`generate()` returns a list of `TestCase`, `TestGroup` or `Generator` objects from `fixturerig.config.model`.
These are inserted at the generator's position in the config.
By default they are wrapped in a test group named after the generator; with `create_group: false` they are inserted directly.

```yaml
- generator:
    name: voltage_sweep
    class: project.generators.VoltageSweep   # def generate(self, voltages: list[float])
    parametermap:
      voltages: [3.3, 4.5, 5.0]
```

```python
from fixturerig.base import Generator
from fixturerig.config.model import TestCase

class VoltageSweep(Generator):
    def generate(self, voltages: list[float]):
        return [TestCase(name=f"voltage_{v}", cls="project.tests.VoltageLimitTest", params={"limit": v})
                for v in voltages]
```

Generators run first, before the env_setup and dut_info steps, so they can't use DUT information. They can't take fixture parameters.
Any problem while generating (unknown class, bad parameters, an exception, an invalid return value) stops the run with a config error.

## env_setup, dut_info, dut_shutdown

These three entry kinds are lifecycle steps. They all have the same shape: `name` and `class` (required), `parametermap` and `parameterpath`.
The class is a subclass of `fixturerig.base.Step` and implements `run()`. The parameters are passed to its `__init__` and `run()` methods, like a testcase's.
A parameter with a Fixture type hint references a configured fixture, as for tests; the fixture is started before `run()` and stopped after it.

```yaml
- env_setup:
    name: "Flash Firmware"
    class: project.setup.FlashFirmware   # def run(self, dut: Dut, path: Path)
    parameterpath:
      path: resources/firmware.bin
- dut_info:
    name: "Collect DUT information"
    class: project.info.Collect          # def run(self) -> dict
```

- Steps are only allowed at the top level of a config file, not inside a testgroup, and generators can't create them.
- They run per stage in the order listed above, in config order within a stage, no matter where they are declared between other entries.
- `run()` may return a mapping, which is reported as a two-column table in the step's report group (`<stage>: <name>`). Any other non-None return value fails the step.
- If an env_setup or dut_info step fails (bad class, bad parameters, a fixture problem, an exception), the remaining setup steps don't run and every test is reported as skipped with the reason.
- dut_shutdown steps always run, all of them, even after a failure or an aborted run. A failed shutdown step is reported but doesn't change any test verdict.
- Steps are not tests and are not counted in the run summary.

## pythonpath

pythonpath behaves like a parameterpath entry in terms of value resolution. So the same code should be reused to support all kinds of path types.
In the end pythonpath entries don't have a (key) name and are anonymous.


## Plugins
## pythonpath entries:
A pythonpath entry is anonymous (it has no name) and its value is a single path value with exactly the parameterpath value syntax and resolution rules:

```yaml
- pythonpath: ..                                         # relative to this config file
- pythonpath: {path: plugins, base_module: my_project}   # relative to a module's directory
- pythonpath: {path: lib, base_path: ../third_party}
```

All pythonpath entries are added to the front of sys.path, in config order, before any configured class is loaded. Each must resolve to an existing local directory.
