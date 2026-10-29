# Write a fixture

A fixture wraps a device or interface: a power supply, a CAN adapter, a DUT connection. Subclass {class}`fixturerig.base.Fixture`, take the rig-specific settings in `__init__` and override only the lifecycle hooks you need.

```python
from fixturerig.base import Fixture


class PowerSupply(Fixture):
    """A bench power supply controlled over a serial port.

    :param port: serial port, e.g. ``COM4`` or ``/dev/ttyUSB0``.
    :param max_voltage: hard limit the fixture refuses to exceed.
    """

    def __init__(self, port: str, max_voltage: float = 30.0):
        self.port = port
        self.max_voltage = max_voltage
        self._conn = None

    # --- device API used by tests ------------------------------------

    def set_voltage(self, volts: float) -> None:
        if volts > self.max_voltage:
            raise ValueError(f"{volts} V exceeds the limit of {self.max_voltage} V")
        self._conn.write(f"VOLT {volts}\n".encode())

    # --- lifecycle ---------------------------------------------------

    def setup(self) -> None:
        self._conn = open_serial(self.port)

    def self_test(self) -> bool:
        return self._conn.query("*IDN?").startswith("ACME")

    def stop(self) -> None:
        self.set_voltage(0.0)

    def teardown(self) -> None:
        self._conn.close()
```

```yaml
- fixture:
    name: power_supply
    class: project.fixtures.PowerSupply
    parametermap:
      port: COM4
      max_voltage: 12.0
```

Fixtures get their config parameters through `__init__` only.

## The lifecycle

| Hook         | When it runs                                                         |
|--------------|----------------------------------------------------------------------|
| `setup`      | Once, when a test first needs the fixture. Connect here.             |
| `self_test`  | Right after `setup`. Return `False` and dependent tests are skipped. |
| `start`      | Before each test that uses the fixture.                              |
| `stop`       | After each test that used the fixture.                               |
| `lazy_stop`  | When the next test no longer needs a fixture the previous one used.  |
| `disconnect` | After the last test, before teardown. Detach safely.                 |
| `teardown`   | After the last test. Release resources.                              |

Fixtures are created lazily and shared by every test that references them. They are torn down in reverse creation order. A fixture that fails `setup` or `self_test` is marked broken, and later tests that need it are skipped instead of retrying the hardware.

## Fixtures that use other fixtures

A fixture's `__init__` can take another fixture, with the same type-hint rule as tests:

```python
class Dut(Fixture):
    def __init__(self, supply: PowerSupply, can: CanBus):
        ...
```

## Fixtures that are always on

Some equipment must run for the whole session, for example a rest-bus simulation. Mark it `autoloaded`:

```yaml
- fixture:
    name: rbs
    class: project.fixtures.RestBusSimulation
    autoloaded: true
```

An autoloaded fixture is created at the very start of the run, before generators and setup steps. It is started and stopped around every test as if every test required it. A test can still declare it as a parameter to get a reference to it. A broken autoloaded fixture skips every test.

## Report from a fixture

Fixtures can use the same `report` API as tests, for example to log what a device returned during `self_test`. See {doc}`reporting`.

## A simulated fixture for experiments

{class}`~fixturerig.fixtures.dummy_fixture.DummyFixture` simulates a device with named numeric registers and records every lifecycle call. Use it to try out configs or to test framework behaviour without hardware.
