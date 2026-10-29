# Debug a test in an IDE

Normally FixtureRig catches an exception from a test, turns it into an `error` verdict and carries on with the next test. That is what you want on a nightly run, but while developing a test you usually want the debugger to stop where the exception was raised.

Add `--interactive`:

```bash
fixturerig --config config/env.yaml --config config/test.yaml --interactive
```

In interactive mode, any exception raised in test, fixture, step or generator code falls through to the top of the program and ends the run. Start the run in an IDE that breaks on uncaught exceptions, and it stops at the root cause.

What still happens:

- Verdict exceptions and configuration problems (class loading, argument mapping, unknown or broken fixtures, a failed self test) are reported as usual.
- Cleanup still runs on the way out: `dut_shutdown` steps, fixture teardown and report finalisation. Cleanup never raises, so the DUT is left in a safe state and the original exception reaches the top unchanged.

## VS Code

Add a launch configuration that runs the `fixturerig` module from your project folder:

```json
{
  "name": "FixtureRig: my rig",
  "type": "debugpy",
  "request": "launch",
  "module": "fixturerig",
  "cwd": "${workspaceFolder}/my_rig",
  "args": ["--config", "config/env.yaml", "--config", "config/test.yaml", "--interactive"],
  "justMyCode": false
}
```

Make sure **Uncaught Exceptions** is ticked in the Breakpoints panel. The repository's `.vscode/launch.json` has a ready-made configuration for the bundled demo.

## From code

Pass `interactive=True` to {class}`~fixturerig.core.runner.RunSession` or {func}`~fixturerig.core.runner.run_all`. See {doc}`library-use`.
