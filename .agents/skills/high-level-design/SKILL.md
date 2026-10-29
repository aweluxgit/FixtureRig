---
name: high-level-design
description: This skill contains a description of the high level design for FixtureRig
---

# FixtureRig High-Level Design

Use this skill when designing, implementing, or reviewing FixtureRig features. FixtureRig is a Python-first, object-oriented test framework for hardware-in-the-loop (HIL) and physical-system testing. Its purpose is to make tests programmer-friendly and AI-friendly while keeping hardware configuration outside test code.

## Product Direction

FixtureRig should let engineers define reusable Python fixtures, device interfaces, test cases, and test generators, then configure concrete instances in human-editable files. The framework should connect generated or handwritten tests to real devices without hiding the device details that matter during debugging.

The core positioning is:

- Python tests for physical systems.
- Configuration-driven setup of test environments and device fixtures.
- Inheritance-aware construction of test and fixture objects.
- Ordered execution with useful logging and reporting.
- Extension points for project-specific devices, tests, generators, and integrations.

The name FixtureRig refers to both the prepared test fixture and the physical rig on which it runs. It does not by itself imply AI; AI assistance is a workflow goal, not a requirement that every framework component depend on an AI service.

## Architectural Shape

Keep the implementation centered on the existing package boundaries:

- `fixturerig.config` parses and models configuration, initially YAML.
- `fixturerig.core.inheritance` analyzes constructor and class inheritance information.
- `fixturerig.core.module_loader` loads configured Python classes and extension modules.
- `fixturerig.core.runner` coordinates setup, test generation, execution, and results.
- `fixturerig.fixtures` contains reusable interfaces and device implementations, such as CAN and power fixtures.
- `fixturerig.base` contains base classes for fixtures and tests.
- `fixturerig.report` contains the report stream, the reportable content (text, tables, charts, images, verdicts), the global `report` proxy and the report modules (console, JSON, HTML, Allure, Excel, PDF, PDF test spec).
- `fixturerig.main` is the command-line entry point.

Prefer existing abstractions and small cooperating modules over a monolithic runner. Device access belongs behind fixture or interface objects, while the runner owns lifecycle and ordering.

Outside of the src directory resides the folloowing directories:

- `demo` contains example configurations and tests. The demo is a demonstration of how to use the framework.


## Configuration-Driven Construction

Configuration is the source of environment-specific values. A test or fixture class should be usable across rigs without embedding ports, device addresses, paths, limits, or calibration values in Python code.

The intended construction heuristic is:

1. Load a configuration tree, including configuration split across files or directories when needed.
2. Resolve a configured class through the module loader.
3. Inspect the class and its bases to determine accepted constructor keyword arguments. For tests, also inspect the `setup`, `test` and `teardown` methods.
4. Match configured names to constructor parameters and inherited parameters, and for tests to the method parameters. A name may match parameters of several methods; a name that matches none is an error.
5. Use type hints to provide IDE support, identify values that represent configured interfaces, and perform automatic conversion where it is unambiguous.
6. Instantiate the object with the resolved keyword arguments.

For example, a test may express its dependency in normal Python:

```python
class VoltageLimitTest:
	def test(self, power_supply: PowerSupply, limit: float):
		power_supply.set_voltage(limit/2)
```

The matching configuration can provide the `power_supply` object and the numeric `limit` without requiring a second, framework-specific dependency declaration:

```yaml
- fixture:
	name: power_supply
	class: fixturerig.fixtures.power.PowerSupply
	port: "COM4"
- testcase:
	name: voltage_limit
	class: project.tests.VoltageLimitTest
	power_supply: power_supply
	limit: 4.5
```

The exact schema is still evolving, so preserve compatibility with the models already present in `fixturerig.config`. Do not silently consume misspelled parameters. Missing required values, ambiguous conversions, unresolved classes, and unexpected parameters should produce actionable errors.

One feature is to use the fixturerig code as a library. In this case a config model can be build up by calling functions that parse config files or arguments and expand the config model each time.

The framework inspects the __init__ method arguments for all classes using configuration based construction. For tests also the test, setup, and teardown method parameters are taken from the config file. For example this might result in the test and setup method to get the same config parameters.

### Values and Conversion

The design anticipates scalar values such as strings, integers, floats, booleans, `None`, paths, lists, and dictionaries. YAML is preferred because it is human-readable, supports comments and nesting, and is a superset of JSON. YAML anchors and aliases may be useful for shared fixture settings.

All external configuration values may need normalization before construction. Use type hints and explicit path rules rather than ad hoc string parsing. Paths should support a portable base or `relative-to` rule so configurations can be moved between machines.

A `parametermap` always has the parameter names as keys. The value can be any literal, a list, or a dict.

A test can have a `fixturemap` entry that maps the fixture names used in the test to the fixture names used in the configuration, in the form `<test fixture name>: <config fixture name>`. It is needed whenever the two names differ.

Do not assume every non-literal value is an object reference until the reference syntax is defined. Reference resolution, complex generic types, subclass-specific parameters, and the behavior for unknown argument names remain design decisions. Implement these rules conservatively and document them in the configuration model.

## Execution Model

Execution is intentionally ordered. There is usually little value in the complexity of arbitrary out-of-order test execution when tests share physical equipment and state.

The intended lifecycle is:

1. Test generation.
2. Environment setup, including restbus or simulation parameters, time synchronization and optional software flashing.
3. DUT information gathering.
4. Test execution in configuration or source order.
5. Result collection and reporting.

Test groups should support hierarchy. A configuration entry may describe a fixture, a test case, a generator, or a group containing other entries. Some entries may be organizational and should not themselves count as tests.

For debugging and test development, the `--interactive` option changes how exceptions are handled. Any exception raised by test, fixture, step or generator code falls through immediately to the top of the program and ends it, instead of being turned into an `error` verdict or a failed step. This lets an IDE that breaks on uncaught exceptions stop at the root cause. Verdict exceptions and configuration problems (class loading, argument mapping, unknown or broken fixtures, a failed self test) are still reported as usual. Cleanup still runs on the way out: dut_shutdown steps, fixture teardown and report finalization. It stays non-raising so the DUT is left in a safe state and the original exception reaches the top unchanged.

When configuration values override one another, use an explicit and deterministic precedence rule. Do not add implicit override behavior until the precedence model is represented in the configuration model and covered by tests.

## Extension Model

Fixtures, test cases, generators, and report modules should be loadable plugins or configured classes. The common extension pattern is a base class with project-specific subclasses or a plugin that overrides selected behavior while retaining access to host state.

Plugins should support these use cases:

- Add DUT-specific behavior to a reusable fixture.
- Customize generated tests for a project.
- Add device drivers or adapters without changing the core.
- Load reporting modules using a mechanism similar to fixture loading.

Keep plugin composition understandable. Plugin chaining, plugins for plugins, and a universal host API are not MVP requirements. If host access is needed, define one canonical API rather than relying on ambiguous names such as `self.host`.

The configuration entries for the extensions above all have a class field. That field contains a python import path in the form of "package.module.class". The python import roots apply when resolving these names.

## Devices and Interoperability

The device layer should provide stable Python-facing interfaces while allowing multiple implementations. Initial areas include power supplies, CAN, XIL, and Ethernet. Hardware-specific drivers should remain replaceable; for example, CAN support may need to work with both open-source adapters and commercial devices.

The minimum useful interoperability boundary is:

- configuration files can describe the environment and devices;
- external systems can invoke selected tests or generated test cases;
- FixtureRig can return generated test identities and results;
- device interfaces remain available to Python tests.

Support for other languages is a future concern. A possible future configuration attribute could identify a non-Python shim, but do not distort the Python object and inheritance model before a concrete integration requires it.

## Observability and User Experience

Logging is part of the core design, not an afterthought. Use the standard logging system and keep framework logs distinguishable from test-development logs through levels, filters, or logger names. Test output should be capturable in reports rather than relying only on console printing.

The likely UI direction is a local web UI for device configuration, interactive tests, and monitoring. A default UI should support unknown devices through a basic self-test response, while richer device-specific views can be added later. WPF is possible for a Windows-only tool, but a web UI keeps the backend more portable.

Reporting should begin with console output and a structured result model, then grow toward HTML and PDF reports. Reports must retain enough context to diagnose failures: selected configuration, fixture identity, test identity, logs, timings, and device or DUT information.


## Reporting

The test framework supports a modular approach to reporting where multiple different reporting modules can be active, all with a different purpose.
Each module filters the relevant messages from a report stream.

Typical report modules are:
- ConsoleReport (active by default)
- PDF report
- HTML report
- Allure report
- Json report
- PDF Test spec reporting (ignores verdicts and just summarizes test specs)
- ColoredConsoleReport
- ExcelReport

The report modules are initialized via the config model. They use the same params format as tests for their configuration parameters.
They also allow the same inheritance model to pass these parameters to their init method.

Reporting uses a concept where tests can only report limited feedback:
- Text
- Tables
- Charts
- Verdicts
- Images? (Unclear use case)

Calling a function that reports one of these events adds them to a report stream and all attached report modules will then pick up these events and add them in an appropriate form into their report.
The framework will also report additional information into the report stream:
- When a test group is started and stopped.
- The test name
- Overall test verdict
- Reference to test management tool for traceability

While a test is running it can use the report function to access the global report stream.

Tables exist in a simple variant with just text inside and a complex variant that can have any element inside including other tables.

## Base classes

There are base classes for fixtures, test cases, and verdics. The base classes provide a common interface for the framework to interact with the fixtures and test cases.
The base classes contain the plugin hooks for the plugin system for fixtures and test cases.
The base classes also contain the common functionality for the fixtures and test cases.

### Test case module

Contains the following methods for the testcase class:
- `setup`: called before the test case is run. Used to setup the test case.
- `test`: called to run the test case itself. This is the only mandatory method.
	The verdict of the test case is determined by the return value of this method. The return value can be a boolean or a verdict object.
	If the test method throws an exception, the test case is considered an error unless the returned exception is inheriting from a verdict_exception. In that case the verdict is determined by the exception.
- `teardown`: called after the test case is run. Used to teardown the test case.

Errors in `setup` and `teardown` affect the test verdict just like errors in `test`. With `--interactive` such an exception is not turned into a verdict; it ends the run (see "Execution Model").

### Generator module

Generators add tests with specific parameters based on additional inputs. Effectively they extend the list of tests in the config model with additional entries.

- Generators are nodes in the config model and can create either additional test groups or tests.
- A generator node has a list of entries that have been generated.
- Generators have a single method, `generate(...)`:
	- `generate()` takes parameters from the configuration in the same way as `test` does for test cases (including `__init__` inheritance and type-hint based conversion).
	- `generate()` returns a list of entries to be inserted into the config model at the generator node.
- Generators must have a `name`, so generators from different config files can be merged.
- The generator's `name` is automatically used as the name of a test group that is attached to the generator node. The entries returned by `generate()` become the entries of that group.
- The generator node has a `create_group` flag, `True` by default. If the config sets it to `false`, no group is created below the generator and the entries returned by `generate()` are added directly to the list of the generator node.
- Generators don't have `setup()` or `teardown()` methods for now.
- Generators run first, before environment setup and DUT information gathering, so a generator can't use DUT information and can't take fixture parameters.
- A generated entry must be a `TestCase`, a `TestGroup` or another `Generator`; nested generators are expanded as well.
- Inside `generate()` the config model module (`fixturerig.config.model`) is used directly to create entries.

Example:

```python
from fixturerig.base import Generator
from fixturerig.config.model import TestCase

class VoltageSweepGenerator(Generator):
	def generate(self, voltages: list[float]):
		return [
			TestCase(name=f"voltage_{v}", cls="project.tests.VoltageLimitTest", params={"limit": v})
			for v in voltages
		]
```

```yaml
- generator:
	name: voltage_sweep
	class: project.generators.VoltageSweepGenerator
	parametermap:
	  voltages: [3.3, 4.5, 5.0]
```

This produces one group `voltage_sweep` containing `voltage_3.3`, `voltage_4.5` and `voltage_5.0`. With `create_group: false` the three test cases are inserted directly at the generator node.

### Fixture module

Contains the following methods for the fixture class:
- `setup`: called before the fixture is used. Used to setup and connect the fixture.
- `self_test`: called after the fixture is setup. Used to perform a self test on the fixture to ensure it is working correctly.
- `start`: called before each test case after the fixture is setup. Used to start the fixture and prepare it for use.
- `stop`: called after each test case when the fixture was used. Used to stop the fixture.
- `lazy_stop`: called when a newly instantiated testcase doesn't require the fixture after the last testcase required it.
- `disconnect`: called after the fixture is used. Used to disconnect the fixture safely from others before teardown.
- `teardown`: called after the fixture is used. Used to teardown the fixture and free resources.

### Verdict module

Contains the following methods for the verdict class:
- `__init__`: called when an instance of the verdict class is created. Used to initialize the verdict.
- `__str__`: called when an instance of the verdict class is converted to a string. Used to provide a string representation of the verdict.
- `__repr__`: called when an instance of the verdict class is represented in a list or other collection. Used to provide a detailed string representation of the verdict.

There are multiple possible verdicts:
- `passed`: the test case passed.
- `failed`: the test case failed.
- `error`: the test case encountered an error or exception that was not handled by the test case.
- `skipped`: the test case was skipped due to a configuration or fixture issue.
- `none`: the test case did not return a verdict. This is considered an error unless the test case is marked as a 'script'. This can't be set by the test itself.
- `knownfailed`: the test case is known to fail and is expected to fail. This is used for tests that are not yet implemented or are known to be broken. This can't be set by the test itself.


## MVP Boundary

The first useful release consists of:

- configuration parsing and validation;
- inheritance-aware object instantiation;
- a test runner with the ordered lifecycle;
- basic logging;
- a console result or report.

Installer packaging, integrated deployment environments, a faster commercial inheritance analyzer, enterprise branding, device monitoring, and rich PDF/HTML reporting are later concerns. Avoid building those features into core APIs prematurely.

## Guidance for AI-Assisted Test Development

FixtureRig is intended to work well with Copilot, Claude Code, and similar agents. Tests should expose clear class names, type hints, docstrings, and configuration examples so an agent can infer available interfaces and generate useful test cases.

An AI-assisted workflow should have a feedback loop:

1. Inspect fixture interfaces, configuration, and DUT constraints.
2. Generate or modify a test using the existing object model.
3. Run the smallest relevant test or self-test on the available rig.
4. Feed failures, logs, and result details back into the next edit.

Agents must distinguish verified behavior from brainstorming notes. They should inspect the current implementation and tests before introducing schema or lifecycle assumptions, and they should prefer a narrow executable check after each meaningful change.

## Design Constraints and Open Decisions

Treat these as explicit follow-up decisions rather than hidden assumptions:

- How should generic and complex types behave across subclasses?
- Should an argument absent from configuration be ignored or rejected?
- What syntax identifies a reference to another fixture?
- How are `None`, paths, f-strings, and other special values represented?
- What is the precedence model for inherited, group, and local parameters?
- How are partial runs and non-test configuration entries reported?
- What canonical API gives plugins access to host state?
- How are external frameworks expected to call tests and consume results?

When implementing a feature that touches one of these areas, make the smallest coherent choice, encode it in the configuration or object model, and add focused tests so the choice can later be changed deliberately.

Define the functionality provided by this skill, including detailed instructions and examples