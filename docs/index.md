# FixtureRig

**Python tests for physical systems.**

FixtureRig is an object-oriented test framework for hardware-in-the-loop (HIL) and other physical-system testing. You write tests and device fixtures as ordinary Python classes. The concrete rig (ports, addresses, limits, calibration values) goes in YAML files outside the code, so the same test runs on any bench by switching the config.

```{note}
FixtureRig is in early development (v{{ release }}). The core loop works: config parsing, inheritance-aware object construction, ordered execution, fixture lifecycle and multi-format reporting. Real device drivers and CLI parameter overrides are not implemented yet, and the config schema may still change.
```

## Why FixtureRig?

Plain Python, no framework DSL
: Dependencies are ordinary method parameters with type hints. A test that needs a power supply declares one as a parameter.

Configuration-driven rigs
: YAML describes which fixtures exist and how they are set up. Tests never hard-code `COM4` or `192.168.0.10`.

Strict, actionable config errors
: Misspelled keys, unknown parameters and missing required values are reported, never silently ignored.

Ordered execution for shared hardware
: Tests run in config order. Fixtures are created once, shared, and driven through an explicit lifecycle.

Reports that help with debugging
: Tests report text, tables, charts and checks into one stream. Console, JSON, HTML, PDF, PDF test spec, Excel and Allure modules all read from it.

Friendly to AI coding agents
: Clear class names, type hints, docstrings and config examples give agents what they need to generate and iterate on tests.

## Where to start

- New to FixtureRig? Follow {doc}`getting-started/installation` and then {doc}`getting-started/first-project`.
- Looking for a specific task, such as writing a fixture or adding a report? See the {doc}`how-to/index`.
- Looking up a config key, a CLI option or a class? See the {doc}`reference/index`.
- Want to understand how a run works? Read {doc}`explanation/index`.

```{toctree}
:hidden:
:caption: Getting started

getting-started/installation
getting-started/first-project
```

```{toctree}
:hidden:
:caption: How-to guides

how-to/index
```

```{toctree}
:hidden:
:caption: Reference

reference/index
```

```{toctree}
:hidden:
:caption: Explanation

explanation/index
```

```{toctree}
:hidden:
:caption: Project

roadmap
contributing
changelog
```
