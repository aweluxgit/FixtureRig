#
# This module runs the configured test generators
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Generator
# module"):
#
# - run_generators expands every Generator node of the config in place, in
#   configuration order (a depth first walk). A generator's config params are
#   mapped onto its __init__ and generate() together, like a testcase's.
#
# - Generators run before any fixture exists, so a generator parameter can't
#   be a fixture reference; such a parameter is a mapping error. Getting DUT
#   information into a generator is left for when that lifecycle phase exists.
#
# - generate() must return a list of TestCase, TestGroup or Generator entries
#   (groups checked recursively). By default they are wrapped in a single
#   TestGroup named after the generator; with `create_group: false` they are
#   stored on the generator node as they are.
#   Generators found in the generated entries are expanded in turn.
#
# - A generated entry without a `source` gets the generator's source, so
#   relative paths in it resolve like those of the generator's config file.
#
# - Any failure - class loading, argument mapping, an exception from
#   generate() or an invalid result - is a GeneratorError. It is a ConfigError,
#   since the configured run cannot be built without the generated entries.
#
# - Expansion happens once per generator (`Generator.generated`), so calling
#   run_generators again - e.g. from run_tests after main already did - is a
#   no-op for generators that have already run.
#

from __future__ import annotations

import logging

from fixturerig.base.generator import Generator as BaseGenerator
from fixturerig.config.model import Config, ConfigEntry, ConfigError
from fixturerig.config.model import Generator as GeneratorEntry
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.config.model import TestGroup
from fixturerig.core.class_loader import ClassLoadError, load_class
from fixturerig.core.inheritance import ArgumentMappingError, map_config_to_methods

logger = logging.getLogger(__name__)

_GENERATED_TYPES = (TestCaseEntry, TestGroup, GeneratorEntry)


class GeneratorError(ConfigError):
    """Raised when a configured generator cannot be run or returns invalid entries."""


def run_generators(config: Config) -> None:
    """Expand every not yet generated Generator node of `config` in place."""
    _expand_entries(config.entries)


def _expand_entries(entries: list[ConfigEntry]) -> None:
    for entry in entries:
        if isinstance(entry, GeneratorEntry):
            if not entry.generated:
                _generate(entry)
            _expand_entries(entry.entries)
        elif isinstance(entry, TestGroup):
            _expand_entries(entry.entries)


def _generate(entry: GeneratorEntry) -> None:
    label = entry.name
    try:
        cls = load_class(entry.cls)
    except ClassLoadError as exc:
        raise GeneratorError(f"Generator {label!r}: {exc}") from exc
    if not issubclass(cls, BaseGenerator):
        raise GeneratorError(f"Generator {label!r}: {entry.cls!r} is not a subclass of fixturerig.base.Generator")

    try:
        init_kwargs, generate_kwargs = map_config_to_methods(entry, [cls, cls.generate])
    except ArgumentMappingError as exc:
        raise GeneratorError(f"Generator {label!r}: {exc}") from exc

    logger.info("Run generator %s (%s)", label, entry.cls)
    try:
        generated = cls(**init_kwargs).generate(**generate_kwargs)
    except Exception as exc:
        raise GeneratorError(f"Generator {label!r}: generate() raised {exc!r}") from exc

    if not isinstance(generated, list):
        raise GeneratorError(
            f"Generator {label!r}: generate() must return a list of entries, got {type(generated).__name__}"
        )
    _check_generated(generated, label)
    for item in generated:
        _set_source(item, entry)
    logger.info("Generator %s generated %d entries", label, len(generated))

    if entry.create_group:
        generated = [TestGroup(entries=generated, name=entry.name, source=entry.source)]
    entry.entries = generated
    entry.generated = True


def _check_generated(entries: list, label: str) -> None:
    for item in entries:
        if not isinstance(item, _GENERATED_TYPES):
            raise GeneratorError(
                f"Generator {label!r}: generate() may only return TestCase, TestGroup or Generator "
                f"entries, got {item!r}"
            )
        if isinstance(item, TestGroup):
            _check_generated(item.entries, label)


def _set_source(item: ConfigEntry, generator: GeneratorEntry) -> None:
    if item.source is None:
        item.source = generator.source
    if isinstance(item, TestGroup):
        for nested in item.entries:
            _set_source(nested, generator)
