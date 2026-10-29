# Configuration format

A config file is a YAML list. Each item is a mapping with exactly one key, the **entry kind**:

```yaml
- pythonpath: ..
- fixture: { ... }
- testcase: { ... }
```

An empty file is allowed and has no entries. Several files given with repeated `--config` options are merged in order; entries with the same name path are [merged](#merging).

FixtureRig is strict: an unknown entry kind, an unknown key, a value of the wrong type or a required key that is still missing after merging is a config error naming the file. Nothing is silently ignored.

## Entry kinds

| Entry | Required keys (after [merging](#merging)) | Optional keys |
|-------|---------------|---------------|
| [`fixture`](#fixture) | `name`, `class` | `parametermap`, `parameterpath`, `autoloaded` |
| [`testcase`](#testcase) | `name`, `class` | `parametermap`, `parameterpath`, `fixturemap`, `traceability`, `option_only` |
| [`testgroup`](#testgroup) | | `name`, `entries` (or a plain list), `option_only` |
| [`generator`](#generator) | `name`, `class` | `parametermap`, `parameterpath`, `create_group`, `option_only` |
| [`report`](#report) | `class` | `name`, `parametermap`, `parameterpath` |
| [`env_setup`, `dut_info`, `dut_shutdown`](#lifecycle-steps) | `name`, `class` | `parametermap`, `parameterpath` |
| [`pythonpath`](#pythonpath) | a path value | |

## Common keys

`name`
: The entry's name. Fixture names are what tests reference.

`class`
: A Python import path, `package.module.Class`. It is resolved against the configured `pythonpath` roots and the normal `sys.path`.

`parametermap`
: A mapping of parameter names to literal values: scalars, lists or mappings. Values are converted according to the parameter's type hint; see {doc}`../explanation/argument-mapping`.

`parameterpath`
: A mapping of parameter names to [path values](#path-values). A parameter may appear in `parametermap` or `parameterpath`, not both.

`option_only`
: `true` turns a `testcase`, `testgroup` or `generator` into a set of options for an entry declared elsewhere; see [merging entries](#merging).

Parameter names are matched by name to the class's constructor parameters, including inherited ones. For test cases and steps they are also matched to the parameters of `setup`, `test`, `teardown` or `run`. A name that matches nothing is an error.

(path-values)=
## Path values

A path value is either a string or a mapping:

```yaml
parameterpath:
  firmware: resources/fw.bin                        # relative to this config file
  calibration: {path: cal.json, base_module: project.data}   # relative to a module's directory
  log_dir: {path: logs, base_path: /var/fixturerig} # relative to a given directory
  spec: https://example.com/spec.pdf               # a URI is passed through
```

`path` (required)
: An absolute path, a relative path or a URI.

`base_module`
: Resolve `path` relative to the directory of this importable module.

`base_path`
: Resolve `path` relative to this directory.

A mapping may give at most one of `base_module` and `base_path`. Without either, a relative path is relative to the **config file**, so configs work from any working directory. A plain string is shorthand for `{path: <string>}`.

(fixture)=
## `fixture`

```yaml
- fixture:
    name: power_supply
    class: project.fixtures.PowerSupply
    autoloaded: false
    parametermap:
      port: COM4
```

`autoloaded` (default `false`)
: Create the fixture at the very start of the run and start and stop it around every test, as if every test required it.

Fixture parameters are passed to `__init__`. See {doc}`../how-to/write-a-fixture`.

(testcase)=
## `testcase`

```yaml
- testcase:
    name: voltage_limit
    class: project.tests.VoltageLimit
    traceability: [REQ-12, REQ-13]
    fixturemap:
      power_supply: psu_bench_2
    parametermap:
      limit: 4.5
```

`traceability`
: A string or a list of strings: requirement or test management IDs. They appear in the reports and the test specification.

`fixturemap`
: Maps a test parameter to a configured fixture with a different name: `<parameter>: <fixture name>`. Every key must be a parameter with a `Fixture` type hint and may not also appear in `parametermap` or `parameterpath`.

A required parameter with a `Fixture` type hint that the config doesn't mention gets the fixture with the same name, so a `fixturemap` is only needed when the names differ. See {doc}`../how-to/write-a-test`.

(testgroup)=
## `testgroup`

```yaml
- testgroup:
    name: regression
    entries:
      - testcase: {name: t1, class: project.tests.T1}
      - testgroup:
          - testcase: {name: t2, class: project.tests.T2}   # anonymous nested group
```

A group organises entries; it is not a test itself. Groups can be nested. An anonymous group can be written as a plain list. Groups can't contain lifecycle steps.

(generator)=
## `generator`

```yaml
- generator:
    name: voltage_sweep
    class: project.generators.VoltageSweep
    create_group: true
    parametermap:
      voltages: [3.3, 4.5, 5.0]
```

`create_group` (default `true`)
: Wrap the generated entries in a test group named after the generator. With `false` they are inserted directly.

See {doc}`../how-to/generators`.

(report)=
## `report`

```yaml
- report:
    name: html
    class: fixturerig.report.html.HtmlReport
    parameterpath:
      path: ../reports/report.html
    parametermap:
      title: "Bench 2"
```

`class` must be a subclass of {class}`~fixturerig.report.ReportModule`. The console report is added automatically unless a console report is configured. See {doc}`../how-to/reporting` for the built-in modules and their parameters.

(lifecycle-steps)=
## `env_setup`, `dut_info`, `dut_shutdown`

```yaml
- env_setup:
    name: "Flash Firmware"
    class: project.setup.FlashFirmware
    parameterpath:
      path: resources/firmware.bin
```

`class` must be a subclass of {class}`~fixturerig.base.Step`. Steps must be top-level entries. See {doc}`../how-to/lifecycle-steps`.

(pythonpath)=
## `pythonpath`

```yaml
- pythonpath: ..                                         # relative to this config file
- pythonpath: {path: plugins, base_module: my_project}   # relative to a module's directory
- pythonpath: {path: lib, base_path: ../third_party}
```

The value is a single [path value](#path-values). Every `pythonpath` entry is added to the front of `sys.path`, in config order, before any configured class is loaded. Each must resolve to an existing local directory.

(merging)=
## Merging entries

Entries with the same kind and **name path** are merged into one entry, within a file and across files. The name path is the names of the enclosing named groups plus the entry's own name. Anonymous groups don't add to it. Fixtures, testcases, named groups, generators, lifecycle steps (of the same stage) and named reports are merged. Unnamed reports and `pythonpath` entries are always added.

So any key may be left out of an entry, as long as the merged entry has it. The required keys in the table above are checked only after all files are merged, and only for entries that will run.

```yaml
# test.yaml
- testgroup:
    name: regression
    entries:
      - testcase: {name: t1, class: project.tests.T1, parametermap: {limit: 4.5}}

# bench_2.yaml: run with --config test.yaml --config bench_2.yaml
- testgroup:
    name: regression
    entries:
      - testcase: {name: t1, parametermap: {limit: 5.0}}
```

An entry with `option_only: true` (testcases, groups and generators) is never run or expanded and is not checked. It only adds its fields to the entry with the same name path, so a file of options never adds tests on its own.

Entries are merged one at a time in config order:

- An entry with a new name path is added. An option-only one stays inactive.
- A later entry merges into the first earlier entry with the same name path. That entry keeps its place, and stays inactive if it is option-only.
- An exception: a regular entry that matches an earlier option-only entry takes it in. The merged entry is active and sits where the regular entry is declared.

When fields are merged, the later entry's values win, except that an option-only entry's values win over a later regular entry's. So an options file can be given before or after the file it changes.

- `class`, `autoloaded` and `create_group` replace the other entry's values when they are given.
- `parametermap`, `parameterpath` and `fixturemap` entries replace those with the same parameter name.
- `traceability` IDs are added.
- Groups merge their entries recursively, using the same rules.

Everything inside an option-only group is option-only too, so it may only hold testcases, groups and generators. A nested `option_only: false` is a config error. Entries created by generators are not merged.

## Execution order

Wherever entries are declared, a run proceeds in this order:

1. autoloaded fixtures
2. generators
3. `env_setup` steps
4. `dut_info` steps
5. test cases, in config order
6. `dut_shutdown` steps (always)
7. fixture teardown

See {doc}`../explanation/execution-model`.

## Not implemented yet

The schema is still evolving. A `precedence` value to control which entry wins a merge, `parameterlist`, typed parameters (such as f-strings) and `--param` overrides are planned but rejected or ignored today. Using `parameterlist` is a config error.
