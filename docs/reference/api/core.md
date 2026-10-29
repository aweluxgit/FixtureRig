# `fixturerig.core`

Class loading, argument mapping and the runner.

## Runner

```{eval-rst}
.. automodule:: fixturerig.core.runner
   :members: RunSession, run_all, run_generators, run_env_setup, run_dut_info, run_tests, run_dut_shutdown, run_test, TestResult, FixtureError
```

## Generators

```{eval-rst}
.. automodule:: fixturerig.core.generator
   :members: expand_generators, GeneratorError
```

## Class loading

```{eval-rst}
.. automodule:: fixturerig.core.class_loader
   :members: load_class, add_python_paths, ClassLoadError
```

## Argument mapping

```{eval-rst}
.. automodule:: fixturerig.core.inheritance
   :members: map_config_to_method_args, map_config_to_methods, ArgumentMappingError
```
