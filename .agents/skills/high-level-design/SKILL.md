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
- `fixturerig.main` is the command-line entry point.

Prefer existing abstractions and small cooperating modules over a monolithic runner. Device access belongs behind fixture or interface objects, while the runner owns lifecycle and ordering.

## Configuration-Driven Construction

Configuration is the source of environment-specific values. A test or fixture class should be usable across rigs without embedding ports, device addresses, paths, limits, or calibration values in Python code.

The intended construction heuristic is:

1. Load a configuration tree, including configuration split across files or directories when needed.
2. Resolve a configured class through the module loader.
3. Inspect the class and its bases to determine accepted constructor keyword arguments.
4. Match configured names to constructor parameters and inherited parameters.
5. Use type hints to provide IDE support, identify values that represent configured interfaces, and perform automatic conversion where it is unambiguous.
6. Instantiate the object with the resolved keyword arguments.

For example, a test may express its dependency in normal Python:

```python
class VoltageLimitTest:
	def __init__(self, power_supply: PowerSupply, limit: float):
		self.power_supply = power_supply
		self.limit = limit
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

### Values and Conversion

The design anticipates scalar values such as strings, integers, floats, booleans, `None`, paths, lists, and dictionaries. YAML is preferred because it is human-readable, supports comments and nesting, and is a superset of JSON. YAML anchors and aliases may be useful for shared fixture settings.

All external configuration values may need normalization before construction. Use type hints and explicit path rules rather than ad hoc string parsing. Paths should support a portable base or `relative-to` rule so configurations can be moved between machines.

Do not assume every non-literal value is an object reference until the reference syntax is defined. Reference resolution, complex generic types, subclass-specific parameters, and the behavior for unknown argument names remain design decisions. Implement these rules conservatively and document them in the configuration model.

## Execution Model

Execution is intentionally ordered. There is usually little value in the complexity of arbitrary out-of-order test execution when tests share physical equipment and state.

The intended lifecycle is:

1. Environment setup, including restbus or simulation parameters.
2. Device setup, including time synchronization and optional software flashing.
3. DUT information gathering.
4. Test generation.
5. Test execution in configuration or source order.
6. Result collection and reporting.

Test groups should support hierarchy. A configuration entry may describe a fixture, a test case, a generator, or a group containing other entries. Some entries may be organizational and should not themselves count as tests.

When configuration values override one another, use an explicit and deterministic precedence rule. Do not add implicit override behavior until the precedence model is represented in the configuration model and covered by tests.

## Extension Model

Fixtures, test cases, and generators should be loadable plugins or configured classes. The common extension pattern is a base class with project-specific subclasses or a plugin that overrides selected behavior while retaining access to host state.

Plugins should support these use cases:

- Add DUT-specific behavior to a reusable fixture.
- Customize generated tests for a project.
- Add device drivers or adapters without changing the core.
- Load reporting modules using a mechanism similar to fixture loading.

Keep plugin composition understandable. Plugin chaining, plugins for plugins, and a universal host API are not MVP requirements. If host access is needed, define one canonical API rather than relying on ambiguous names such as `self.host`.

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