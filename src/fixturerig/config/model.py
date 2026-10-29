#
# This module holds the configuration model
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Design
# Constraints and Open Decisions", for the open items these narrow down):
#
# - A config document is a flat or nested list of entries. Every entry is
#   exactly one of a Fixture, a TestCase, a Report, a PythonPath, a TestGroup,
#   a Generator or a Step. Groups nest other
#   entries but are not themselves tests - see high-level-design's
#   "Test groups should support hierarchy... organizational and should not
#   themselves count as tests".
#
# - Parameters are a plain {name: value} mapping. Values from a
#   "parametermap" are YAML scalars/collections, taken literally. Values from
#   a "parameterpath" are ConfigPath objects (see below). Reference syntax
#   (pointing at another fixture by name) and typed parameters (e.g.
#   f-strings) are explicitly deferred - see parse_yaml.py's module
#   docstring. Do not guess at that syntax here.
#
# - Every entry records the file it was declared in (`source`), the default
#   base for relative paths.
#
# - ConfigPath is the one path type of the config: it holds every path
#   value, whether it comes from a `parameterpath` section or a `pythonpath`
#   entry, and they all share the same syntax and resolution rules.
#
# - A ConfigPath is resolved late, not while parsing: a parameter path when
#   params are mapped onto a constructor (core/inheritance.py), a pythonpath
#   when it is added to sys.path (core/class_loader.py). So a `base_module`
#   only has to be importable by the time the path is used - for instance
#   thanks to an earlier pythonpath entry. Resolution rules (see
#   .agents/skills/config-format/SKILL.md, "Fields for parameterpath"):
#     * `path` is required: an absolute path, a relative path or a URI.
#     * `base_module` and `base_path` are mutually exclusive bases for a
#       relative `path`. `base_module` names an importable module or package;
#       its directory is the base (a package's own directory, a plain
#       module's containing directory). A relative `base_path` is itself
#       relative to the config file.
#     * Without a base, a relative `path` is relative to the directory of the
#       config file - or to the working directory for entries built in code
#       without a `source`.
#     * An absolute `path` ignores any base.
#     * A "file://" URI resolves to its local path. Any other URI (e.g.
#       "https://...") is passed through as a string; it can't be used for a
#       Path-typed parameter.
#     * Resolved paths are absolute and normalized ("a/../b" -> "b"); they
#       need not exist, so output paths can be configured.
#
# - Merging config (Config.extend, and within one file too) merges entries
#   by name path: the names of the enclosing named groups plus the entry's
#   own name (anonymous groups don't add to it). Fixtures, testcases, named
#   testgroups, generators, steps (of the same stage) and named reports with
#   the same kind and name path are one entry; the first one keeps its place.
#   Anonymous groups, unnamed reports and pythonpaths are just appended. This
#   is a deliberately small, explicit rule, not a stand-in for the full
#   inherited/group/local precedence model called out as an open decision;
#   there is no `precedence` field yet.
#
# - Because any entry can be completed by another one, no field is required
#   while parsing: a missing `class` or `name` is None. Config.validate()
#   checks the merged model instead: every active fixture, testcase,
#   generator and step needs a name and a class, every active report a class.
#   read_config_files calls it once all files are merged.
#
# - TestCase, TestGroup and Generator entries may be `option_only`. Such an
#   entry is never run or expanded: walk() and the runner skip it together
#   with everything nested in it, and validate() doesn't check it. It only
#   contributes its fields to another entry with the same name path.
#   merge_entries implements the rules, applied entry by entry in
#   configuration order:
#     * An entry with a new name path is added as it is; an option_only one
#       stays inactive.
#     * A later entry merges into the first earlier entry with the same name
#       path, which keeps its place and its option_only flag...
#     * ...except that a regular entry matching an earlier option_only entry
#       takes that entry into its own place: they are merged and the result
#       is active.
#   Fields merge with the later entry's values on top, except that an
#   earlier option_only entry's values win over a later regular entry's.
#   Scalars (`class`, `autoloaded`, `create_group`) are replaced when given
#   (not None), params and fixturemap entries replace those with the same
#   name in either mapping, traceability IDs are added. Groups merge their
#   entries recursively, with the same rules.
#   Everything nested in an option_only group is option_only too, so it can
#   only hold testcases, groups and generators (the parser enforces this).
#   Entries created by generators are not merged.
#
# - A PythonPath entry is anonymous: it holds just one ConfigPath, a
#   directory to put on sys.path so configured classes can be imported from
#   it. It may appear anywhere, including inside groups; it always applies to
#   the whole run.
#
# - A Report entry configures one report module (see fixturerig.report). It
#   uses the same `class` + `parametermap` shape as fixtures and testcases,
#   and its params are mapped onto the module's __init__ with the same
#   inheritance-aware mapping. Report modules are global to the run: a report
#   entry nested in a group still reports the whole run.
#
# - A TestCase may carry `traceability`: a list of opaque IDs into a test
#   management tool (e.g. "JIRA-123"). They are reported with the test and
#   not interpreted by the framework.
#
# - A Generator entry configures a test generator class (see
#   fixturerig.base.Generator and core/generator.py). It has a required
#   `name` (so generators can be told apart when config files are merged), a
#   `class`, params and a `create_group` flag (None, not configured, means
#   True). Its `entries`
#   hold what has been generated: empty until the generator runs, then a
#   single TestGroup named after the generator that holds the returned
#   entries - or, with create_group False, the returned entries themselves. Generated entries may only be TestCases,
#   TestGroups and Generators (nested generators are expanded too), so
#   generators never add fixtures, reports or pythonpaths. `generated` records
#   that the generator has run, so expansion happens exactly once.
#
# - A Fixture may be `autoloaded` (the design notes also call these
#   "persistent" fixtures). An autoloaded fixture is created at the very
#   start of the run, before any other entry is executed, and behaves as if
#   every testcase required it under its configured name (see
#   core/runner.py).
#
# - A TestCase may carry a `fixturemap`: {test parameter name: configured
#   fixture name}, for a fixture parameter whose name differs from the
#   fixture's configured name. It is kept apart from `params` so a mapped
#   name can only ever resolve to a fixture, never be passed as a string.
#
# - A Step is one entry of a lifecycle stage around the tests: `env_setup`,
#   `dut_info` or `dut_shutdown` (see STAGES and fixturerig.base.Step). All
#   three share one entry type, told apart by `stage`; it has a required
#   `name`, a `class` and params, like a generator. Steps only make sense for the whole run, so they are only
#   allowed at the top level of a config file, never inside a group, and
#   generators can't create them. They run per stage, in configuration order
#   within each stage (see core/runner.py), no matter where between the
#   other entries they are declared.
#

from __future__ import annotations

import importlib.util
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Union
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


class ConfigError(Exception):
    """Raised for structurally or semantically invalid configuration."""


# A scheme of two or more characters, so a Windows drive ("C:/x") is not a URI.
_URI_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]+://")


def is_uri(value: str) -> bool:
    """Whether `value` looks like a URI ("scheme://..."), not a local path."""
    return bool(_URI_RE.match(value))


@dataclass(frozen=True)
class ConfigPath:
    """A path value from the config (a `parameterpath` value or a `pythonpath`
    entry), resolved on use.

    See the module docstring for the resolution rules.
    """

    path: str
    base_module: str | None = None
    base_path: str | None = None
    source: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path:
            raise ConfigError(f"'path' must be a non-empty string, got {self.path!r}")
        if self.base_module is not None and self.base_path is not None:
            raise ConfigError(
                f"path {self.path!r}: 'base_module' and 'base_path' are mutually exclusive"
            )
        for key in ("base_module", "base_path"):
            value = getattr(self, key)
            if value is not None and (not isinstance(value, str) or not value):
                raise ConfigError(f"path {self.path!r}: {key!r} must be a non-empty string, got {value!r}")

    def __str__(self) -> str:
        if self.base_module is not None:
            return f"{self.path} (relative to module {self.base_module})"
        if self.base_path is not None:
            return f"{self.path} (relative to {self.base_path})"
        return self.path

    @property
    def is_uri(self) -> bool:
        """True for a URI other than file://, which resolve() returns unchanged."""
        return is_uri(self.path) and not self.path.lower().startswith("file://")

    def resolve(self) -> Path | str:
        """Return the absolute local Path, or the URI string for a non-file URI.

        :raises ConfigError: if `base_module` cannot be found.
        """
        if self.is_uri:
            return self.path
        if self.path.lower().startswith("file://"):
            parsed = urlparse(self.path)
            local = url2pathname(unquote(parsed.path))
            if parsed.netloc and parsed.netloc != "localhost":
                local = f"//{parsed.netloc}{local}"  # UNC share
            return _normalize(Path(local))

        path = Path(self.path)
        if path.is_absolute():
            return _normalize(path)
        return _normalize(self._base() / path)

    def _base(self) -> Path:
        config_dir = self.source.parent if self.source is not None else Path()
        if self.base_path is not None:
            return config_dir / self.base_path
        if self.base_module is not None:
            return _module_dir(self.base_module, self.path)
        return config_dir


def _module_dir(name: str, path: str) -> Path:
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError) as exc:
        raise ConfigError(f"path {path!r}: base_module {name!r} cannot be found: {exc}") from exc
    if spec is None:
        raise ConfigError(f"path {path!r}: base_module {name!r} cannot be found")
    if spec.submodule_search_locations:  # a package, including namespace packages
        return Path(next(iter(spec.submodule_search_locations)))
    if spec.origin is None or spec.origin in ("built-in", "frozen"):
        raise ConfigError(f"path {path!r}: base_module {name!r} has no directory")
    return Path(spec.origin).parent


def _normalize(path: Path) -> Path:
    return Path(os.path.normpath(path.absolute()))


# A parameter value is taken as a literal YAML scalar or collection (str, int,
# float, bool, None, list, dict). See module docstring: reference syntax and
# typed/path parameters are not modeled yet.
ParamValue = Any
ParamMap = dict[str, ParamValue]


@dataclass
class Fixture:
    """A configured, reusable device or interface instance."""

    name: str | None
    cls: str | None
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None
    autoloaded: bool | None = None


@dataclass
class TestCase:
    """A configured test instance."""

    name: str | None
    cls: str | None
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None
    traceability: list[str] = field(default_factory=list)
    fixturemap: dict[str, str] = field(default_factory=dict)
    option_only: bool = False


@dataclass
class Report:
    """A configured report module, attached to the run's report stream."""

    cls: str | None
    params: ParamMap = field(default_factory=dict)
    name: str | None = None
    source: Path | None = None


@dataclass
class PythonPath:
    """An anonymous directory to add to sys.path before classes are loaded."""

    path: ConfigPath
    source: Path | None = None


@dataclass
class TestGroup:
    """An organizational grouping of nested entries. Not a test itself."""

    entries: list["ConfigEntry"] = field(default_factory=list)
    name: str | None = None
    source: Path | None = None
    option_only: bool = False


@dataclass
class Generator:
    """A configured test generator. Its `entries` are filled in when it runs."""

    name: str | None
    cls: str | None
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None
    create_group: bool | None = None
    entries: list["ConfigEntry"] = field(default_factory=list)
    generated: bool = False
    option_only: bool = False


# Lifecycle stages a Step can belong to, in the order they run. The
# generators run before env_setup, the tests between dut_info and dut_shutdown.
STAGES = ("env_setup", "dut_info", "dut_shutdown")


@dataclass
class Step:
    """A configured step of one lifecycle stage, e.g. flashing firmware in env_setup."""

    stage: str
    name: str | None
    cls: str | None
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ConfigError(f"Unknown stage {self.stage!r} for step {self.name!r}, expected one of {list(STAGES)}")


ConfigEntry = Union[Fixture, TestCase, Report, PythonPath, TestGroup, Generator, Step]


@dataclass
class Config:
    """The parsed configuration tree, as loaded from one or more files."""

    entries: list[ConfigEntry] = field(default_factory=list)

    def extend(self, other: "Config") -> None:
        """Add another Config's top level entries after this one's.

        Later files' entries come after earlier files' entries, except that
        entries with the same name path are merged (see merge_entries).
        """
        merge_entries(self.entries, other.entries)

    def validate(self) -> None:
        """Check that every active entry is complete, once all config is merged.

        :raises ConfigError: for an entry that lacks a required field.
        """
        for entry in self.walk():
            for required in _REQUIRED.get(type(entry), ()):
                if getattr(entry, required) is None:
                    key = "class" if required == "cls" else required
                    raise ConfigError(f"{entry.source}: {_describe(entry)} has no {key!r}")

    def walk(self) -> Iterator[ConfigEntry]:
        """Yield every active entry, including entries nested inside groups.

        option_only entries and everything nested in them are skipped.
        """
        yield from _walk_entries(self.entries)

    def fixtures(self) -> list[Fixture]:
        return [entry for entry in self.walk() if isinstance(entry, Fixture)]

    def testcases(self) -> list[TestCase]:
        return [entry for entry in self.walk() if isinstance(entry, TestCase)]

    def reports(self) -> list[Report]:
        return [entry for entry in self.walk() if isinstance(entry, Report)]

    def generators(self) -> list[Generator]:
        return [entry for entry in self.walk() if isinstance(entry, Generator)]

    def python_paths(self) -> list[PythonPath]:
        return [entry for entry in self.walk() if isinstance(entry, PythonPath)]

    def steps(self, stage: str | None = None) -> list[Step]:
        """The configured steps, in configuration order; only those of `stage` if given."""
        if stage is not None and stage not in STAGES:
            raise ConfigError(f"Unknown stage {stage!r}, expected one of {list(STAGES)}")
        return [
            entry
            for entry in self.walk()
            if isinstance(entry, Step) and (stage is None or entry.stage == stage)
        ]


def _walk_entries(entries: list[ConfigEntry]) -> Iterator[ConfigEntry]:
    for entry in entries:
        if not is_active(entry):
            continue
        yield entry
        if isinstance(entry, (TestGroup, Generator)):
            yield from _walk_entries(entry.entries)


# The entry kinds that can be option_only.
_OPTION_KINDS = (TestCase, TestGroup, Generator)

# The fields Config.validate() requires of an active entry, per kind.
_REQUIRED: dict[type, tuple[str, ...]] = {
    Fixture: ("name", "cls"),
    TestCase: ("name", "cls"),
    Generator: ("name", "cls"),
    Step: ("name", "cls"),
    Report: ("cls",),
}


def _describe(entry: ConfigEntry) -> str:
    kind = entry.stage if isinstance(entry, Step) else type(entry).__name__.lower()
    return f"{kind} {entry.name!r}" if entry.name is not None else f"unnamed {kind}"


def is_active(entry: ConfigEntry) -> bool:
    """False for an option_only entry, which is never run or expanded."""
    return not (isinstance(entry, _OPTION_KINDS) and entry.option_only)


def merge_entries(entries: list[ConfigEntry], incoming: list[ConfigEntry]) -> None:
    """Add `incoming` after `entries`, merging entries with the same name path.

    `entries` is changed in place. See the module docstring for the rules.
    """
    for entry in incoming:
        _merge_entry(entries, entries, entry)


def _merge_entry(scope: list[ConfigEntry], place: list[ConfigEntry], entry: ConfigEntry) -> None:
    """Merge `entry` with a match in `scope`, or append it to `place`."""
    if isinstance(entry, TestGroup) and entry.name is None:
        # An anonymous group doesn't add to the name path, so its entries are
        # matched in the enclosing scope.
        group = TestGroup(entries=[], name=None, source=entry.source, option_only=entry.option_only)
        place.append(group)
        for nested in entry.entries:
            _merge_entry(scope, group.entries, nested)
        return

    key = _key(entry)
    found = _find(scope, key) if key is not None else None
    if found is None:
        if isinstance(entry, TestGroup):
            # Its own entries may have to be merged with one another.
            nested, entry.entries = entry.entries, []
            merge_entries(entry.entries, nested)
        place.append(entry)
        return
    container, index = found
    existing = container[index]
    if not is_active(existing) and is_active(entry):
        del container[index]
        place.append(_activate(existing, entry))
    else:
        _overlay(existing, entry)


def _key(entry: ConfigEntry) -> tuple | None:
    """What identifies `entry` among its siblings, or None if it is never merged."""
    if isinstance(entry, PythonPath) or entry.name is None:
        return None
    return (type(entry), entry.stage if isinstance(entry, Step) else None, entry.name)


def _find(entries: list[ConfigEntry], key: tuple) -> tuple[list[ConfigEntry], int] | None:
    """The first entry with `key` in `entries`, looking into anonymous groups."""
    for index, candidate in enumerate(entries):
        if _key(candidate) == key:
            return entries, index
        if isinstance(candidate, TestGroup) and candidate.name is None:
            found = _find(candidate.entries, key)
            if found is not None:
                return found
    return None


def _activate(option: ConfigEntry, entry: ConfigEntry) -> ConfigEntry:
    """Merge the earlier option_only entry `option` into the regular `entry`, option values winning."""
    if isinstance(entry, TestGroup):
        # Groups have no fields of their own to merge, so keep their entries
        # in configuration order.
        merge_entries(option.entries, entry.entries)
        entry.entries = option.entries
    else:
        _overlay(entry, option)
    return entry


def _overlay(base: ConfigEntry, overlay: ConfigEntry) -> None:
    """Merge `overlay`'s fields into `base`, overlay values winning."""
    if isinstance(base, TestGroup):
        merge_entries(base.entries, overlay.entries)
        return
    if overlay.cls is not None:
        base.cls = overlay.cls
    overlay_fixturemap = overlay.fixturemap if isinstance(overlay, TestCase) else {}
    base.params = {
        name: value for name, value in base.params.items() if name not in overlay_fixturemap
    } | overlay.params
    if isinstance(base, TestCase):
        base.fixturemap = {
            name: fixture for name, fixture in base.fixturemap.items() if name not in overlay.params
        } | overlay.fixturemap
        base.traceability = base.traceability + [
            ref for ref in overlay.traceability if ref not in base.traceability
        ]
    if isinstance(base, Fixture) and overlay.autoloaded is not None:
        base.autoloaded = overlay.autoloaded
    if isinstance(base, Generator) and overlay.create_group is not None:
        base.create_group = overlay.create_group
