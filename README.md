# FixtureRig

**Python tests for physical systems.**

FixtureRig is an object-oriented test framework for hardware-in-the-loop (HIL) and other physical-system testing. You write tests and device fixtures as ordinary Python classes. The concrete rig (ports, addresses, limits, calibration values) goes in YAML files outside the code. The same test then runs on any bench by switching the config.

> **Status: early development (v0.1.0).** The core loop works: config parsing, inheritance-aware object construction, ordered execution, fixture lifecycle and multi-format reporting. Real device drivers (CAN, power supplies, ...) and CLI parameter overrides are not implemented yet. Expect the config schema to change.

📖 **Documentation:** <https://aweluxgit.github.io/FixtureRig/>

## Why FixtureRig?

- **Plain Python, no framework DSL.** A test that needs a power supply declares one as a typed parameter.
- **Configuration-driven rigs.** YAML describes which fixtures exist and how they are set up. Tests never hard-code `COM4` or `192.168.0.10`.
- **Strict, actionable config errors.** Misspelled keys, unknown parameters and missing required values are reported, never silently ignored.
- **Ordered execution for shared hardware.** Tests run in config order. Fixtures are created once, shared, and driven through an explicit lifecycle.
- **Reports that help with debugging.** Console, JSON, HTML, PDF, PDF test spec, Excel and Allure reports, all from one report stream.
- **Easy for AI agents to work with.** Clear class names, type hints, docstrings and config examples give coding agents what they need.

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/aweluxgit/FixtureRig.git
cd FixtureRig
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run the bundled demo. It uses a simulated device, so no hardware is needed:

```bash
cd demo/test_02
fixturerig --config config/env.yaml --config config/test.yaml
```

The reports are written to `demo/reports/test_02/`.

## A test in 30 seconds

```python
from fixturerig.base import TestCase
from fixturerig.fixtures.dummy_fixture import DummyFixture
from fixturerig.report import report


class VoltageRamp(TestCase):
    """Ramps the simulated supply up to `volt` and checks it stays within `limit`."""

    def test(self, dummy: DummyFixture, volt: float, limit: float) -> bool:
        dummy.write("voltage", volt)
        reading = dummy.read("voltage")
        return report.check(reading <= limit, f"{reading:.2f} V <= {limit} V")
```

```yaml
# config/env.yaml: the rig
- pythonpath: ..
- fixture:
    name: dummy
    class: fixturerig.fixtures.dummy_fixture.DummyFixture

# config/test.yaml: what to run
- testcase:
    name: voltage_ramp
    class: tests.voltage.VoltageRamp
    parametermap:
      volt: 4.5
      limit: 6.0
```

```bash
fixturerig --config config/env.yaml --config config/test.yaml
```

The `dummy: DummyFixture` type hint is all FixtureRig needs to hand the test the configured fixture. `volt` and `limit` come from the config, converted by their type hints.

The [tutorial](docs/getting-started/first-project.md) walks through this step by step.

## Documentation

| Section | Contents |
|---------|----------|
| [Getting started](docs/getting-started/installation.md) | Installation and a first project |
| [How-to guides](docs/how-to/index.md) | Tests, fixtures, setup steps, generators, reports, debugging, library use |
| [Reference](docs/reference/index.md) | Config format, command line, Python API |
| [Explanation](docs/explanation/index.md) | Architecture, execution model, argument mapping |

Build the HTML docs locally:

```bash
pip install -e ".[docs]"
sphinx-build -b html docs docs/_build/html
```

## Development

A VS Code dev container is included (`.devcontainer/`). Run the tests with `pytest`. See [Contributing](docs/contributing.md) for the integration tests, the docs build and building a wheel.

## License

[MIT](LICENSE) © 2026 Alexander Werth
