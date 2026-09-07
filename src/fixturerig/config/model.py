#
# This module holds the configuration model
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Design
# Constraints and Open Decisions", for the open items these narrow down):
#
# - A config document is a flat or nested list of entries. Every entry is
#   exactly one of a Fixture, a TestCase, or a TestGroup. Groups nest other
#   entries but are not themselves tests - see high-level-design's
#   "Test groups should support hierarchy... organizational and should not
#   themselves count as tests".
#
# - Parameters are a "parametermap": a plain {name: value} mapping of YAML
#   scalars/collections, taken literally. Reference syntax (pointing at
#   another fixture by name), path values with relto/basepath, and typed
#   parameters (e.g. f-strings) are explicitly deferred - see
#   parse_yaml.py's module docstring. Do not guess at that syntax here.
#
# - Every entry records the file it was declared in (`source`), so future
#   relative-path resolution has a base to resolve against.
#
# - No override/precedence behavior lives in this model yet. Merging
#   multiple config files is simple append order (Config.extend); this is a
#   deliberately small, explicit rule, not a stand-in for the full
#   inherited/group/local precedence model called out as an open decision.
#

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Union


class ConfigError(Exception):
    """Raised for structurally or semantically invalid configuration."""


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


@dataclass
class TestCase:
    """A configured test instance."""

    name: str
    cls: str
    params: ParamMap = field(default_factory=dict)
    source: Path | None = None


@dataclass
class TestGroup:
    """An organizational grouping of nested entries. Not a test itself."""

    entries: list["ConfigEntry"] = field(default_factory=list)
    name: str | None = None
    source: Path | None = None


ConfigEntry = Union[Fixture, TestCase, TestGroup]


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
            if isinstance(entry, TestGroup):
                yield from _walk_entries(entry.entries)

    def fixtures(self) -> list[Fixture]:
        return [entry for entry in self.walk() if isinstance(entry, Fixture)]

    def testcases(self) -> list[TestCase]:
        return [entry for entry in self.walk() if isinstance(entry, TestCase)]


def _walk_entries(entries: list[ConfigEntry]) -> Iterator[ConfigEntry]:
    for entry in entries:
        yield entry
        if isinstance(entry, TestGroup):
            yield from _walk_entries(entry.entries)
