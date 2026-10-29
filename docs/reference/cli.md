# Command line

```text
fixturerig --config PATH [--config PATH ...] [--param KEY=VALUE ...] [--interactive]
python -m fixturerig ...
```

## Options

`--config PATH`
: A YAML config file. Required at least once. Repeat it to merge several files; they are merged in the order given, later entries after earlier ones.

`--param KEY=VALUE`
: Override a top-level parameter. May be given multiple times, but each key only once.

  ```{warning}
  Overrides are parsed and validated but **not applied yet**: the precedence model is still being designed. FixtureRig logs a warning naming the ignored keys.
  ```

`--interactive`
: Let any exception raised in a test, fixture, step or generator end the program, instead of being reported as an `error` verdict. Use it with an IDE that breaks on uncaught exceptions. See {doc}`../how-to/debugging`.

`--version`
: Print the version and exit.

`-h`, `--help`
: Print the help and exit.

## Exit codes

| Code | Meaning |
|------|---------|
| `0`  | The run completed. Failed or skipped tests don't change the exit code. |
| `1`  | Configuration error: invalid YAML, unknown keys, a class that can't be loaded, a failing generator, ... |
| `2`  | Invalid command line arguments |

## Logging

FixtureRig logs through the standard {mod}`logging` module under the `fixturerig` logger, at level `INFO`, to stderr. Test output that belongs in the report should go through `report`, not `print` or logging.
