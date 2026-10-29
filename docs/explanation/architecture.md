# Architecture

FixtureRig separates three things that test frameworks for hardware often mix up:

- **What a test does** lives in Python classes: tests, fixtures, steps, generators.
- **Which rig it runs on** lives in YAML: ports, addresses, limits, calibration values, which fixture class drives which device.
- **How a run proceeds** is owned by the runner: ordering, fixture lifecycle, verdicts and reporting.

A test class therefore contains no rig details and can run unchanged on any bench whose config provides the fixtures it asks for.

## Packages

```text
fixturerig/
  base/       Classes you subclass: Fixture, TestCase, Step, Generator, Verdict
  config/     The config model and the YAML and command line parsers
  core/       Class loading, argument mapping, generator expansion, the runner
  fixtures/   Reusable fixtures (currently DummyFixture, a simulated device)
  report/     The report stream, report elements, events and report modules
  main.py     The command-line entry point
```

```text
 YAML files ──► config.parse_yaml ──► config.model.Config
                                          │
                     core.class_loader ◄──┤  (class paths)
                     core.inheritance  ◄──┤  (parameters → method arguments)
                                          ▼
                                    core.runner ──► your Fixture / TestCase / Step objects
                                          │
                                          ▼
                                  report.ReportStream ──► report modules (console, HTML, PDF, ...)
```

## Design principles

Plain Python, no DSL
: A test declares what it needs as typed method parameters. There is no second, framework-specific dependency declaration, which keeps tests readable for people, IDEs and AI coding agents alike.

Config is the only source of rig-specific values
: Tests and fixtures never embed ports, addresses or limits. The config can be split across files: one for the bench, one for the test selection.

Fail loudly on config mistakes
: Misspelled keys, unknown parameters, missing values and unresolvable classes are errors with the file and entry named. A silently ignored typo on a hardware rig can mean a test that passes without checking anything.

Ordered execution
: Tests share physical equipment and state, so they run strictly in config order. There is no reordering or parallelism.

The core is a library
: The `fixturerig` command is a thin wrapper around functions that another test system can call directly. See {doc}`../how-to/library-use`.

## Reporting model

Tests can report only a few kinds of content: text, tables, charts, images and verdicts. Each call becomes an event in one {class}`~fixturerig.report.ReportStream`. The framework adds its own events around it: run, group and test start and finish, including each test's description, parameters and traceability IDs.

Every report module receives the events it accepts and renders them in its own format. Adding a report format never touches tests, and a test never knows which reports are active.

## Extension points

Every configurable piece is a class loaded by import path: fixtures, tests, steps, generators and report modules. Extending FixtureRig for a project means subclassing a base class and naming the subclass in the config. No registration or plugin manifest is needed.
