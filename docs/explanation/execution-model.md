# The execution model

## Phases

A run goes through fixed phases, whatever order the entries appear in:

1. **Autoloaded fixtures** are created, set up and self-tested.
2. **Generators** expand into test entries. A failing generator stops the run with a config error before the rig is touched.
3. **`env_setup` steps** prepare the environment, for example flash firmware.
4. **`dut_info` steps** collect information about the device under test.
5. **Tests** run in config order, as a depth-first walk of the groups.
6. **`dut_shutdown` steps** always run, even after failures or an aborted run.
7. **Fixture teardown**: every created fixture gets `disconnect()` and then `teardown()`, in reverse creation order.

If an `env_setup` or `dut_info` step fails, the remaining setup steps are skipped and every test is reported as skipped with the reason. Testing an unprepared DUT would only produce misleading results.

## Fixture lifecycle around tests

Fixtures are created lazily, when the first test (or step, or other fixture) references them, and then shared.

```text
first use:        __init__ → setup → self_test
each test:        start → [test.setup → test.test → test.teardown] → stop
next test without it:   lazy_stop
end of run:       disconnect → teardown
```

A fixture that fails `setup` or `self_test` is remembered as broken. Later tests that need it are skipped immediately instead of retrying the hardware.

Autoloaded fixtures behave as if every test required them.

## Verdicts

Every test ends with exactly one verdict:

`passed`
: `test()` returned `True` or a passed verdict, and no reported check failed.

`failed`
: `test()` returned `False` or a failed verdict, or a `report.check()` failed.

`error`
: An unexpected exception in `setup()` or `test()`. An exception in `teardown()` or a fixture's `start()`/`stop()` turns an otherwise passed result into `error`.

`skipped`
: The test never ran: its class couldn't be loaded, its parameters didn't match, a fixture it needs is broken, or a setup step failed. A test can also skip itself.

`none`
: `test()` returned nothing. Counted as not passed.

`knownfailed`
: Reserved for tests registered as expected to fail; not used yet.

Tests can only produce `passed`, `failed` and `skipped` themselves. The other statuses are reserved for the runner.

## Interactive mode

With `--interactive`, exceptions from test, fixture, step and generator code are re-raised instead of becoming verdicts, so an IDE can break where they happen. Cleanup still runs on the way out. See {doc}`../how-to/debugging`.
