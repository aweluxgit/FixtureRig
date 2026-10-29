# How config values become arguments

FixtureRig constructs every configured object (fixtures, tests, steps, generators, report modules) from its config entry. This page describes how values in `parametermap` and `parameterpath` reach Python parameters.

## Matching by name

Config keys are matched to parameter **names**. Which methods are searched depends on the kind of object:

| Kind | Methods |
|------|---------|
| Fixture, report module | `__init__` |
| Test case | `__init__`, `setup`, `test`, `teardown` |
| Lifecycle step | `__init__`, `run` |
| Generator | `__init__`, `generate` |

Every method gets each key it names, so the same value can reach several methods. A key that no method takes is an error, and so is a required parameter that no key provides. Positional-only parameters and `*args` are never filled.

## Inherited parameters

A subclass often only adds its own parameters and forwards the rest:

```python
class LabSupply(PowerSupply):
    def __init__(self, channel: int, **kwargs):
        super().__init__(**kwargs)
        self.channel = channel
```

A signature with `**kwargs` doesn't say which names it accepts, so FixtureRig walks the class hierarchy (the MRO) to find the methods that declare the remaining names. Here `port` and `max_voltage` are matched to `PowerSupply.__init__`. The walk stops at the first method without `**kwargs`. Any key still unmatched after that is an error.

## Conversion by type hint

The type hint decides how a raw YAML value is converted:

| Hint | Conversion |
|------|------------|
| none or `Any` | passed through unchanged |
| `bool`, `int`, `float`, `str` | coerced from a string if needed; `"yes"`, `"on"`, `"1"` and `"true"` are true |
| `Path` | coerced from a string; a URI is an error rather than a mangled path |
| `Optional[T]`, `T \| None` | `None` passes through, anything else is converted to `T` |
| `list[T]`, `dict[K, V]` | each element converted recursively |
| a `Fixture` subclass | the value is a fixture **name**, resolved to the configured fixture |
| anything else | passed through unchanged |

Values from `parameterpath` are resolved to paths first (see {ref}`path values <path-values>`), then converted like any other value.

## Fixture references

A parameter is only treated as a fixture reference when its type hint is a {class}`~fixturerig.base.Fixture` subclass. Plain string parameters are never mistaken for references. The fixture is found in this order:

1. the name given in `fixturemap`,
2. the value given in `parametermap`,
3. the parameter's own name, if the parameter is required.

The resolved object must be an instance of the hinted class.

## Why so strict?

On a hardware rig, a silently ignored typo such as `limt: 4.5` can mean a test that runs against a default and passes without checking what it should. FixtureRig prefers stopping with a clear message to guessing.
