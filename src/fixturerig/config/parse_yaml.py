#
# This module contains the code that parses the yaml files into the configuration model
#
#
# Design decision:
# Keep track of which configuration file contained which path parameter to resolve config relative paths.
# Paths can be relative to the config, a python module or a basepath.
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
#         - path: {name: "somepath", path = ..., relto = ..., basepath = ... }
#       parameterpath:
#         somepath: {path = ..., relto = ... }
# ---
# - parametermap:
#     some
#
# Implemented, conservative subset of the schema above (see model.py for the
# reasoning):
#
# - The document root must be a YAML list (or empty/null, treated as no
#   entries).
# - Each list item is a single-key mapping: "fixture", "testcase", or
#   "testgroup". Any other shape, key count, or kind is a ConfigError -
#   misspelled keys are rejected, never silently ignored or dropped.
# - fixture/testcase bodies accept exactly `name` (required), `class`
#   (required), and `parametermap` (optional mapping of literal values).
#   `parameterlist`/`parameterpath`/typed params/path params from the
#   schema sketch above are not implemented yet; using them raises a clear
#   ConfigError rather than being silently accepted or misparsed.
# - testgroup bodies accept either a bare list of nested entries (an
#   anonymous group, matching the sketch above) or a mapping of
#   {name, entries} for a named group. Nested entries follow the same
#   rules, recursively.
# - Every parsed entry records the source file path, for future relative
#   path resolution.

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from fixturerig.config.model import (
    Config,
    ConfigEntry,
    ConfigError,
    Fixture,
    TestCase,
    TestGroup,
)

_FIXTURE_REQUIRED_KEYS = {"name", "class"}
_FIXTURE_ALLOWED_KEYS = _FIXTURE_REQUIRED_KEYS | {"parametermap"}

_TESTCASE_REQUIRED_KEYS = {"name", "class"}
_TESTCASE_ALLOWED_KEYS = _TESTCASE_REQUIRED_KEYS | {"parametermap"}

_TESTGROUP_REQUIRED_KEYS: set[str] = set()
_TESTGROUP_ALLOWED_KEYS = _TESTGROUP_REQUIRED_KEYS | {"name", "entries"}


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


def load_config(paths: list[str | Path]) -> Config:
    """Parse and merge multiple config files, in the order given.

    See Config.extend for the (currently simple, append-only) merge rule.
    """
    config = Config(entries=[])
    for path in paths:
        config.extend(parse_yaml_file(path))
    return config


def _parse_entry(item: Any, source: Path) -> ConfigEntry:
    if not isinstance(item, dict) or len(item) != 1:
        raise ConfigError(
            f"{source}: each config entry must be a single-key mapping "
            f"('fixture', 'testcase', or 'testgroup'), got {item!r}"
        )

    ((kind, body),) = item.items()

    if kind == "fixture":
        return _parse_fixture(body, source)
    if kind == "testcase":
        return _parse_testcase(body, source)
    if kind == "testgroup":
        return _parse_testgroup(body, source)

    raise ConfigError(
        f"{source}: unknown config entry kind {kind!r}, expected "
        f"'fixture', 'testcase', or 'testgroup'"
    )


def _require_mapping(body: Any, source: Path, kind: str) -> dict:
    if not isinstance(body, dict):
        raise ConfigError(f"{source}: {kind} body must be a mapping, got {type(body).__name__}")
    return body


def _check_keys(body: dict, allowed: set[str], required: set[str], source: Path, kind: str) -> None:
    unknown = set(body) - allowed
    if unknown:
        raise ConfigError(
            f"{source}: unknown key(s) {sorted(unknown)} in {kind}, allowed: {sorted(allowed)}"
        )
    missing = required - set(body)
    if missing:
        raise ConfigError(f"{source}: {kind} missing required key(s) {sorted(missing)}")


def _parse_params(body: dict, source: Path, kind: str) -> dict:
    params = body.get("parametermap", {})
    if not isinstance(params, dict):
        raise ConfigError(
            f"{source}: {kind} parametermap must be a mapping, got {type(params).__name__}"
        )
    return dict(params)


def _parse_fixture(body: Any, source: Path) -> Fixture:
    body = _require_mapping(body, source, "fixture")
    _check_keys(body, _FIXTURE_ALLOWED_KEYS, _FIXTURE_REQUIRED_KEYS, source, "fixture")
    return Fixture(
        name=body["name"],
        cls=body["class"],
        params=_parse_params(body, source, "fixture"),
        source=source,
    )


def _parse_testcase(body: Any, source: Path) -> TestCase:
    body = _require_mapping(body, source, "testcase")
    _check_keys(body, _TESTCASE_ALLOWED_KEYS, _TESTCASE_REQUIRED_KEYS, source, "testcase")
    return TestCase(
        name=body["name"],
        cls=body["class"],
        params=_parse_params(body, source, "testcase"),
        source=source,
    )


def _parse_testgroup(body: Any, source: Path) -> TestGroup:
    if isinstance(body, list):
        # Anonymous group: `testgroup: [<entry>, ...]`.
        nested = [_parse_entry(item, source) for item in body]
        return TestGroup(entries=nested, name=None, source=source)

    body = _require_mapping(body, source, "testgroup")
    _check_keys(body, _TESTGROUP_ALLOWED_KEYS, _TESTGROUP_REQUIRED_KEYS, source, "testgroup")
    nested_body = body.get("entries", [])
    if not isinstance(nested_body, list):
        raise ConfigError(
            f"{source}: testgroup entries must be a list, got {type(nested_body).__name__}"
        )
    nested = [_parse_entry(item, source) for item in nested_body]
    return TestGroup(entries=nested, name=body.get("name"), source=source)
