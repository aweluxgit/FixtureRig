# Use FixtureRig from another test system

The `fixturerig` command is a thin wrapper. The same building blocks can be called from Python, for example from a larger test system or a CI script.

## Run everything

```python
from pathlib import Path

from fixturerig.config.model import Config
from fixturerig.config.parse_yaml import read_config_files
from fixturerig.core.class_loader import add_python_paths
from fixturerig.core.runner import run_all
from fixturerig.report.loader import build_report_stream

config = Config(entries=[])
read_config_files(config, [Path("config/env.yaml"), Path("config/test.yaml")])
add_python_paths(config)

stream = build_report_stream(config)
try:
    results = run_all(config, stream)
finally:
    stream.close()

for r in results:
    print(r.name, r.verdict, f"{r.duration:.3f}s")
```

- {func}`~fixturerig.config.parse_yaml.read_config_files` merges the files into the config in order.
- {func}`~fixturerig.core.class_loader.add_python_paths` applies the `pythonpath` entries, so configured classes can be imported.
- {func}`~fixturerig.report.loader.build_report_stream` creates the configured report modules. Closing the stream makes them write their files.
- {func}`~fixturerig.core.runner.run_all` returns one {class}`~fixturerig.core.runner.TestResult` per test.

## Run the phases yourself

To add your own work between the phases, call them one by one inside a {class}`~fixturerig.core.runner.RunSession`, as `fixturerig.main` does:

```python
from fixturerig.core.runner import (
    RunSession, run_dut_info, run_dut_shutdown, run_env_setup, run_generators, run_tests,
)

with RunSession(config, stream) as session:
    try:
        run_generators(session)
        run_env_setup(session)
        run_dut_info(session)
        my_custom_preparation()
        run_tests(session)
    finally:
        run_dut_shutdown(session)
```

Entering the session creates the autoloaded fixtures and activates the report stream. Leaving it tears down every fixture and reports the run summary, also when a phase raises.

## Build the config in code

The config model is a list of plain dataclasses, so you can add entries without YAML:

```python
from fixturerig.config.model import Fixture, TestCase

config.entries.append(Fixture(name="dummy", cls="fixturerig.fixtures.dummy_fixture.DummyFixture"))
config.entries.append(TestCase(name="t1", cls="tests.voltage.VoltageRamp", params={"volt": 4.5, "limit": 6.0}))
```

## Errors

Configuration problems raise {class}`~fixturerig.config.model.ConfigError`. Test failures don't raise; they are in the results.
