---
name: config-format
description: Detailed descriptions of the config format with examples.
---

## Format

Config files are in yaml format and parsed into an internal config model.


Available options in the config files:
- fixture
- testcase
- testgroup
- generator
- report
- plugin
- pythonpath
- parameters
- env_setup
- dut_setup
- dut_info
- dut_shutdown


Common subfields for fixture, testcase, generator, report, and plugin entries:
- name
- class
- parametermap
- parameterlist
- parameterpath

The entries are run in order:
- env_setup
- dut_setup
- dut_info
- generator
- testcase
- dut_shutdown


## Fields for parameterpath

The keys for all parameterpath entries are the parameter names.
The value can either be a string or a dictionary.
If it's a string it will be treated as if it's a dictionary with just the path entry.
Otherwise the dictionary can have these entries:
- path
    absolute path, relative path or uri
    if relative and no other base specified then it's relative to the config file
- base_module
    if it exists the path is relative to the directory of this module
- base_path
    if it exists the path is relative to this path

If the value for a parampath is a string and not a dict then it's a shorthand for the path field of the parampath entry.

## pythonpath

pythonpath behaves like a parameterpath entry in terms of value resolution. So the same code should be reused to support all kinds of path types.
In the end pythonpath entries don't have a (key) name and are anonymous.


## Plugins
## pythonpath entries:
A pythonpath entry is anonymous (it has no name) and its value is a single path value with exactly the parameterpath value syntax and resolution rules:

```yaml
- pythonpath: ..                                         # relative to this config file
- pythonpath: {path: plugins, base_module: my_project}   # relative to a module's directory
- pythonpath: {path: lib, base_path: ../third_party}
```

All pythonpath entries are added to the front of sys.path, in config order, before any configured class is loaded. Each must resolve to an existing local directory.
