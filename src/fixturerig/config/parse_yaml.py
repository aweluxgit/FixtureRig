#
# This module contains the code that parses the yaml files into the configuration model
#
#
# Design decision:
# Keep track of which configuration file contained which path parameter to resolve config relative paths.
# Paths can be relative to the config, a python module or a base path
# (see "parameterpath" below and ConfigPath in model.py).
#
# Example config:
# ---
# - fixture:
#     name: "Can"
#     class: ...
# - testcase:
#     name: "sometest"
#     class: ....
#     parametermap:
#       volt: 4.5
#       limit: 6.0
# - testgroup:
#   - testcase:
#       name: "foo"
#       class: ....
#       parameterlist:
#         - param: {name: "...", value: 4}
#         - param: {name: "...", value: 4, type= "fstring"}
#         - path: {name: "somepath", path: ..., base_module: ..., base_path: ... }
#       parameterpath:
#         somepath: {path: ..., base_module: ... }
#         otherpath: ../relative/to/this/config/file
# ---
# - parametermap:
#     some
#
# Implemented, conservative subset of the schema above (see model.py for the
# reasoning):
#
# - The document root must be a YAML list (or empty/null, treated as no
#   entries).
# - Each list item is a single-key mapping: "fixture", "testcase", "report",
#   "pythonpath", "testgroup", "generator", or one of the lifecycle stages
#   "env_setup", "dut_info" and "dut_shutdown". Any other shape,
#   key count, or kind is a ConfigError - misspelled keys are rejected, never
#   silently ignored or dropped.
# - No key of an entry body is required here. An entry may be completed by
#   another entry with the same name path, in the same or a later file (see
#   the merge rules in config/model.py), so a missing `name` or `class` is
#   None in the model. read_config_files checks the merged model with
#   Config.validate(): every active fixture, testcase, generator and step
#   needs `name` and `class`, every active report `class`. Below, "required"
#   means required by that check.
# - fixture/testcase bodies accept exactly `name` (required), `class`
#   (required), `parametermap` (optional mapping of literal values) and
#   `parameterpath` (optional mapping of path parameters). fixture bodies
#   additionally accept `autoloaded` (optional boolean, default false; None
#   in the model when not given, so it doesn't override a merged value).
#   `parameterlist` and typed params from the schema sketch above are not
#   implemented yet; using them raises a clear ConfigError rather than being
#   silently accepted or misparsed.
# - parameterpath maps a parameter name to either a string (shorthand for
#   {path: <string>}) or a mapping with `path` (required) and at most one of
#   `base_module` / `base_path`. Each becomes a ConfigPath (model.py), stored
#   in the entry's params next to the parametermap values and resolved when
#   the object is created. A name given in both parametermap and
#   parameterpath is a ConfigError.
# - A pythonpath entry is anonymous; its value is a single path value with
#   exactly the parameterpath value syntax (and the same parser), e.g.
#     - pythonpath: ..
#     - pythonpath: {path: lib, base_module: some.package}
# - testcase bodies additionally accept `traceability`: a string or a list of
#   strings referencing a test management tool.
# - testcase bodies also accept `fixturemap`: a mapping of test parameter
#   names to configured fixture names, e.g.
#     fixturemap:
#       power_supply: psu_bench_2
#   Keys and values must be strings, and a key may not also appear in
#   parametermap or parameterpath.
# - report bodies accept `class` (required), `name`, `parametermap` and
#   `parameterpath` (all optional), e.g.
#     - report:
#         class: fixturerig.report.json_report.JsonReport
#         parameterpath:
#           path: ../reports/results.json
# - generator bodies accept `name` and `class` (required), `parametermap`,
#   `parameterpath` and `create_group` (optional boolean, default true; None
#   in the model when not given), e.g.
#     - generator:
#         name: voltage_sweep
#         class: project.generators.VoltageSweep
#         parametermap:
#           voltages: [3.3, 4.5, 5.0]
#   The generated entries are not part of the config file; they are added
#   when the generator runs (see core/generator.py).
# - env_setup, dut_info and dut_shutdown bodies all accept `name`
#   and `class` (required), `parametermap` and `parameterpath`, e.g.
#     - env_setup:
#         name: "Flash Firmware"
#         class: project.setup.FlashFirmware
#         parameterpath:
#           path: resources/firmware.bin
#   Each becomes a Step of that stage. Steps are only allowed at the top
#   level of a file; one inside a testgroup is a ConfigError.
# - testgroup bodies accept either a bare list of nested entries (an
#   anonymous group, matching the sketch above) or a mapping of
#   {name, entries} for a named group. Nested entries follow the same
#   rules, recursively.
# - testcase, generator and named testgroup bodies accept `option_only`
#   (optional boolean, default false); see config/model.py for how such an
#   entry is merged. An option_only entry is never checked by validate(),
#   e.g. to change a parameter of a testcase declared in another file:
#     - testgroup:
#         name: regression
#         option_only: true
#         entries:
#           - testcase: {name: t1, parametermap: {limit: 5.0}}
#   Everything nested in an option_only group is option_only too: a nested
#   `option_only: false` is a ConfigError, and so is any entry other than a
#   testcase, testgroup or generator.
# - Every parsed entry records the source file path; it is also stored on
#   every ConfigPath as the default base for relative paths.

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from fixturerig.config.model import (
    Config,
    ConfigEntry,
    ConfigError,
    ConfigPath,
    Fixture,
    Generator,
    STAGES,
    PythonPath,
    Report,
    Step,
    TestCase,
    TestGroup,
)

# No key is required while parsing: an entry may be completed by another one
# with the same name path. Config.validate() checks the merged model.
_NAMED_KEYS = {"name", "class", "parametermap", "parameterpath"}
_PARAMPATH_KEYS = {"path", "base_module", "base_path"}

_FIXTURE_ALLOWED_KEYS = _NAMED_KEYS | {"autoloaded"}
_TESTCASE_ALLOWED_KEYS = _NAMED_KEYS | {"traceability", "fixturemap", "option_only"}
_REPORT_ALLOWED_KEYS = _NAMED_KEYS
_GENERATOR_ALLOWED_KEYS = _NAMED_KEYS | {"create_group", "option_only"}
_STEP_ALLOWED_KEYS = _NAMED_KEYS
_TESTGROUP_ALLOWED_KEYS = {"name", "entries", "option_only"}

# The entry kinds that can be option_only, and so may appear in an option_only group.
_OPTION_KINDS = ("testcase", "testgroup", "generator")


_KINDS = ", ".join(
    repr(kind) for kind in ("fixture", "testcase", "report", "pythonpath", "testgroup", "generator", *STAGES)
)


def parse_yaml_file(path: str | Path) -> Config:
    """Parse a single YAML config file into a Config tree."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read config file {path}: {exc}") from exc

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if document is None:
        return Config(entries=[])

    if not isinstance(document, list):
        raise ConfigError(
            f"{path}: top level config must be a list of entries, got {type(document).__name__}"
        )

    entries = [_parse_entry(item, path) for item in document]
    return Config(entries=entries)


def read_config_files(config, paths: list[str | Path]) -> Config:
    """Parse and merge multiple config files, in the order given.

    See Config.extend for the merge rule. The merged config is then checked
    with Config.validate().
    """
    for path in paths:
        config.extend(parse_yaml_file(path))
    config.validate()
    return config


def _parse_entry(item: Any, source: Path, in_option_group: bool = False) -> ConfigEntry:
    if not isinstance(item, dict) or len(item) != 1:
        raise ConfigError(
            f"{source}: each config entry must be a single-key mapping "
            f"({_KINDS}), got {item!r}"
        )

    ((kind, body),) = item.items()

    if in_option_group and kind not in _OPTION_KINDS:
        raise ConfigError(
            f"{source}: {kind} is not allowed inside an option_only testgroup, "
            f"only {', '.join(repr(k) for k in _OPTION_KINDS)}"
        )

    if kind == "fixture":
        return _parse_fixture(body, source)
    if kind == "testcase":
        return _parse_testcase(body, source, in_option_group)
    if kind == "report":
        return _parse_report(body, source)
    if kind == "pythonpath":
        return PythonPath(path=_parse_path_value(body, source, "pythonpath"), source=source)
    if kind == "testgroup":
        return _parse_testgroup(body, source, in_option_group)
    if kind == "generator":
        return _parse_generator(body, source, in_option_group)
    if kind in STAGES:
        return _parse_step(kind, body, source)

    raise ConfigError(f"{source}: unknown config entry kind {kind!r}, expected {_KINDS}")


def _require_mapping(body: Any, source: Path, kind: str) -> dict:
    if not isinstance(body, dict):
        raise ConfigError(f"{source}: {kind} body must be a mapping, got {type(body).__name__}")
    return body


def _check_keys(body: dict, allowed: set[str], source: Path, kind: str) -> None:
    unknown = set(body) - allowed
    if unknown:
        raise ConfigError(
            f"{source}: unknown key(s) {sorted(unknown)} in {kind}, allowed: {sorted(allowed)}"
        )


def _parse_option_only(body: dict, source: Path, kind: str, in_option_group: bool) -> bool:
    option_only = body.get("option_only", in_option_group)
    if not isinstance(option_only, bool):
        raise ConfigError(f"{source}: {kind} option_only must be true or false, got {option_only!r}")
    if in_option_group and not option_only:
        raise ConfigError(
            f"{source}: {kind} {body.get('name')!r} is inside an option_only testgroup "
            f"and can't set option_only to false"
        )
    return option_only


def _parse_params(body: dict, source: Path, kind: str) -> dict:
    params = _section(body, "parametermap", source, kind)
    paths = _section(body, "parameterpath", source, kind)

    both = sorted(set(params) & set(paths))
    if both:
        raise ConfigError(
            f"{source}: {kind} parameter(s) {both} given in both parametermap and parameterpath"
        )

    merged = dict(params)
    for name, value in paths.items():
        merged[name] = _parse_path_value(value, source, f"{kind} parameterpath {name!r}")
    return merged


def _section(body: dict, key: str, source: Path, kind: str) -> dict:
    section = body.get(key, {})
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ConfigError(f"{source}: {kind} {key} must be a mapping, got {type(section).__name__}")
    return section


def _parse_path_value(value: Any, source: Path, what: str) -> ConfigPath:
    """Parse any path value of the config: a string, or a {path, base_module | base_path} mapping."""
    where = f"{source}: {what}"
    if isinstance(value, str):
        value = {"path": value}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a string or a mapping, got {type(value).__name__}")
    unknown = sorted(set(value) - _PARAMPATH_KEYS)
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {unknown}, allowed: {sorted(_PARAMPATH_KEYS)}")
    if "path" not in value:
        raise ConfigError(f"{where}: missing required key 'path'")
    try:
        return ConfigPath(
            path=value["path"],
            base_module=value.get("base_module"),
            base_path=value.get("base_path"),
            source=source,
        )
    except ConfigError as exc:
        raise ConfigError(f"{where}: {exc}") from exc


def _parse_fixture(body: Any, source: Path) -> Fixture:
    body = _require_mapping(body, source, "fixture")
    _check_keys(body, _FIXTURE_ALLOWED_KEYS, source, "fixture")
    autoloaded = body.get("autoloaded")
    if autoloaded is not None and not isinstance(autoloaded, bool):
        raise ConfigError(f"{source}: fixture autoloaded must be true or false, got {autoloaded!r}")
    return Fixture(
        name=body.get("name"),
        cls=body.get("class"),
        params=_parse_params(body, source, "fixture"),
        source=source,
        autoloaded=autoloaded,
    )


def _parse_testcase(body: Any, source: Path, in_option_group: bool = False) -> TestCase:
    body = _require_mapping(body, source, "testcase")
    option_only = _parse_option_only(body, source, "testcase", in_option_group)
    _check_keys(body, _TESTCASE_ALLOWED_KEYS, source, "testcase")
    params = _parse_params(body, source, "testcase")
    return TestCase(
        name=body.get("name"),
        cls=body.get("class"),
        params=params,
        source=source,
        traceability=_parse_traceability(body, source),
        fixturemap=_parse_fixturemap(body, params, source),
        option_only=option_only,
    )


def _parse_fixturemap(body: dict, params: dict, source: Path) -> dict[str, str]:
    fixturemap = _section(body, "fixturemap", source, "testcase")
    bad = {k: v for k, v in fixturemap.items() if not isinstance(k, str) or not isinstance(v, str)}
    if bad:
        raise ConfigError(
            f"{source}: testcase fixturemap must map parameter names to fixture names, got {bad!r}"
        )
    both = sorted(set(fixturemap) & set(params))
    if both:
        raise ConfigError(
            f"{source}: testcase parameter(s) {both} given in both fixturemap and parametermap/parameterpath"
        )
    return dict(fixturemap)


def _parse_traceability(body: dict, source: Path) -> list[str]:
    refs = body.get("traceability", [])
    if isinstance(refs, (str, int)):
        refs = [refs]
    if not isinstance(refs, list) or not all(isinstance(ref, (str, int)) for ref in refs):
        raise ConfigError(
            f"{source}: testcase traceability must be a string or a list of strings, got {refs!r}"
        )
    return [str(ref) for ref in refs]


def _parse_report(body: Any, source: Path) -> Report:
    body = _require_mapping(body, source, "report")
    _check_keys(body, _REPORT_ALLOWED_KEYS, source, "report")
    return Report(
        cls=body.get("class"),
        params=_parse_params(body, source, "report"),
        name=body.get("name"),
        source=source,
    )


def _parse_generator(body: Any, source: Path, in_option_group: bool = False) -> Generator:
    body = _require_mapping(body, source, "generator")
    option_only = _parse_option_only(body, source, "generator", in_option_group)
    _check_keys(body, _GENERATOR_ALLOWED_KEYS, source, "generator")
    create_group = body.get("create_group")
    if create_group is not None and not isinstance(create_group, bool):
        raise ConfigError(f"{source}: generator create_group must be true or false, got {create_group!r}")
    return Generator(
        name=body.get("name"),
        cls=body.get("class"),
        params=_parse_params(body, source, "generator"),
        source=source,
        create_group=create_group,
        option_only=option_only,
    )


def _parse_step(stage: str, body: Any, source: Path) -> Step:
    body = _require_mapping(body, source, stage)
    _check_keys(body, _STEP_ALLOWED_KEYS, source, stage)
    return Step(
        stage=stage,
        name=body.get("name"),
        cls=body.get("class"),
        params=_parse_params(body, source, stage),
        source=source,
    )


def _parse_testgroup(body: Any, source: Path, in_option_group: bool = False) -> TestGroup:
    if isinstance(body, list):
        # Anonymous group: `testgroup: [<entry>, ...]`.
        nested = [_parse_entry(item, source, in_option_group) for item in body]
        _check_no_steps(nested, source)
        return TestGroup(entries=nested, name=None, source=source, option_only=in_option_group)

    body = _require_mapping(body, source, "testgroup")
    _check_keys(body, _TESTGROUP_ALLOWED_KEYS, source, "testgroup")
    option_only = _parse_option_only(body, source, "testgroup", in_option_group)
    nested_body = body.get("entries", [])
    if not isinstance(nested_body, list):
        raise ConfigError(
            f"{source}: testgroup entries must be a list, got {type(nested_body).__name__}"
        )
    nested = [_parse_entry(item, source, option_only) for item in nested_body]
    _check_no_steps(nested, source)
    return TestGroup(entries=nested, name=body.get("name"), source=source, option_only=option_only)


def _check_no_steps(entries: list[ConfigEntry], source: Path) -> None:
    for entry in entries:
        if isinstance(entry, Step):
            raise ConfigError(
                f"{source}: {entry.stage} {entry.name!r} is not allowed inside a testgroup; "
                f"lifecycle steps apply to the whole run and must be top level entries"
            )
