# Prepare the rig and the DUT

Work that has to happen before or after all tests, rather than per test, goes into **lifecycle steps**. Typical examples: flash firmware, read the DUT's serial number, power the DUT down safely.

There are three stages:

| Entry          | Runs                     | Typical use                                |
|----------------|--------------------------|--------------------------------------------|
| `env_setup`    | after generators         | flash software, configure the environment  |
| `dut_info`     | after `env_setup`        | collect serial number and versions         |
| `dut_shutdown` | after the tests, always  | leave the DUT in a safe state              |

## Write a step

Subclass {class}`fixturerig.base.Step` and implement `run()`:

```python
import hashlib
from pathlib import Path

from fixturerig.base import Step
from fixturerig.report import report

from project.fixtures import Dut


class FlashFirmware(Step):
    """Flashes the firmware image to the DUT."""

    def run(self, dut: Dut, path: Path):
        image = path.read_bytes()
        report.text(f"Flashing {path.name} ({len(image)} bytes)")
        dut.flash(image)
        return {"file": path.name, "sha256": hashlib.sha256(image).hexdigest()}


class CollectInfo(Step):
    """Reads identification data from the DUT."""

    def run(self, dut: Dut):
        return {"serial_number": dut.serial(), "software_version": dut.sw_version()}
```

```yaml
- env_setup:
    name: "Flash Firmware"
    class: project.setup.FlashFirmware
    parameterpath:
      path: resources/firmware.bin

- dut_info:
    name: "Collect DUT information"
    class: project.setup.CollectInfo

- dut_shutdown:
    name: "Power down"
    class: project.setup.PowerDown
```

Parameters are passed to `__init__` and `run()` exactly as for test cases. A fixture parameter references a configured fixture; the fixture is started before `run()` and stopped after it.

## What `run()` returns

- `None`: nothing extra is reported.
- A mapping: reported as a two-column table in the step's report group, named `<stage>: <name>`.
- Anything else fails the step.

Raise an exception to fail a step.

## When a step fails

- If an `env_setup` or `dut_info` step fails, the remaining setup steps don't run and **every test is reported as skipped** with the reason. Tests on an unprepared rig are meaningless.
- `dut_shutdown` steps **always** run, all of them, even after a failure or an aborted run. A failed shutdown step is reported but doesn't change any test verdict.

## Rules

- Steps must be top-level entries. They can't appear inside a `testgroup` and generators can't create them.
- Within a stage, steps run in config order, wherever they are declared between other entries.
- Steps are not tests and are not counted in the run summary.
