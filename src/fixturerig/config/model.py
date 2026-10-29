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
# - No override/precedence behavior lives in this model yet. Merging
#   multiple config files is simple append order (Config.extend); this is a
#   deliberately small, explicit rule, not a stand-in for the full
#   inherited/group/local precedence model called out as an open decision.
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
#   `class`, params and a `create_group` flag (default True). Its `entries`
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

    name: str
    cls: str
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None
    autoloaded: bool = False


@dataclass
class TestCase:
    """A configured test instance."""

    name: str
    cls: str
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None
    traceability: list[str] = field(default_factory=list)
    fixturemap: dict[str, str] = field(default_factory=dict)


@dataclass
class Report:
    """A configured report module, attached to the run's report stream."""

    cls: str
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


@dataclass
class Generator:
    """A configured test generator. Its `entries` are filled in when it runs."""

    name: str
    cls: str
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None
    create_group: bool = True
    entries: list["ConfigEntry"] = field(default_factory=list)
    generated: bool = False


# Lifecycle stages a Step can belong to, in the order they run. The
# generators run before env_setup, the tests between dut_info and dut_shutdown.
STAGES = ("env_setup", "dut_info", "dut_shutdown")


@dataclass
class Step:
    """A configured step of one lifecycle stage, e.g. flashing firmware in env_setup."""

    stage: str
    name: str
    cls: str
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
        """Append another Config's top level entries after this one's.

        This is the entire multi-file merge rule for now: later files'
        entries come after earlier files' entries. See module docstring.
        """
        self.entries.extend(other.entries)

    def walk(self) -> Iterator[ConfigEntry]:
        """Yield every entry, including entries nested inside groups."""
        for entry in self.entries:
            yield entry
            if isinstance(entry, (TestGroup, Generator)):
                yield from _walk_entries(entry.entries)

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
        yield entry
        if isinstance(entry, (TestGroup, Generator)):
            yield from _walk_entries(entry.entries)
