#
# This module handles loading python modules and classes by path
#
# Design decision (see .agents/skills/high-level-design/SKILL.md):
#
# - Config entries (Fixture.cls / TestCase.cls) name a class as a single
#   dotted string, e.g. "fixturerig.fixtures.power.PowerSupply" - the
#   equivalent of `from fixturerig.fixtures.power import PowerSupply as
#   <result>`. load_class splits that on the *last* "." into a module path
#   and a class name, imports the module, and looks up the class on it.
#   A dotted name pointing at a nested class (e.g. "module.Outer.Inner")
#   is not supported by this split and is left as a later concern.
#
# - Failures at every step (malformed name, missing module, missing
#   attribute, an attribute that isn't a class) raise ClassLoadError with
#   an actionable message - see high-level-design's "unresolved classes...
#   should produce actionable errors".
#
# - `pythonpath` config entries are applied by add_python_paths() before any
#   configured class is loaded. Each is resolved like every other config path
#   (ConfigPath, config/model.py) and must be an existing local directory - a
#   URI, a file or a missing directory is a ConfigError, so a typo surfaces
#   immediately instead of as a confusing ImportError later.
#   Entries are inserted at the front of sys.path, in config order (like
#   PYTHONPATH), so project modules are found before installed packages.
#   Entries already on sys.path are not added again. Entries are applied one
#   by one, so a later entry's `base_module` may come from an earlier entry.
#

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

from fixturerig.config.model import Config, ConfigError

logger = logging.getLogger(__name__)


class ClassLoadError(Exception):
    """Raised when a configured class name cannot be resolved and imported."""


def load_class(full_class_name: str) -> type:
    """
    Loads a class given its fully qualified dotted name.

    Equivalent to `from <module_path> import <class_name>`, e.g.
    `load_class("fixturerig.fixtures.power.PowerSupply")` imports
    `fixturerig.fixtures.power` and returns its `PowerSupply` attribute.

    :param full_class_name: The fully qualified "module.path.ClassName".
    :return: The resolved class object.
    :raises ClassLoadError: if the name is malformed, the module can't be
        imported, the class isn't found on it, or the resolved attribute
        isn't a class.
    """
    if not isinstance(full_class_name, str) or "." not in full_class_name:
        raise ClassLoadError(
            f"Expected a fully qualified 'module.path.ClassName', got {full_class_name!r}"
        )

    module_path, _, class_name = full_class_name.rpartition(".")

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ClassLoadError(
            f"Could not import module {module_path!r} for class {full_class_name!r}: {exc}"
        ) from exc

    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ClassLoadError(f"Module {module_path!r} has no attribute {class_name!r}") from exc

    if not isinstance(cls, type):
        raise ClassLoadError(
            f"{full_class_name!r} does not resolve to a class (got {type(cls).__name__})"
        )

    return cls


def add_python_paths(config: Config) -> list[Path]:
    """Put the directories of every `pythonpath` config entry on sys.path.

    :return: the directories that were added (already present ones are skipped).
    :raises ConfigError: if an entry is not an existing local directory.
    """
    added: list[Path] = []
    for entry in config.python_paths():
        where = f"{entry.source}: " if entry.source else ""
        resolved = entry.path.resolve()
        if isinstance(resolved, str):
            raise ConfigError(f"{where}pythonpath {resolved!r} is a URI; it must be a local directory")
        if not resolved.is_dir():
            raise ConfigError(f"{where}pythonpath {str(entry.path)!r} resolves to {resolved}, which is not a directory")
        if str(resolved) in sys.path:
            continue
        # Insert after the entries added before, keeping config order.
        sys.path.insert(len(added), str(resolved))
        added.append(resolved)
        logger.debug("Added %s to the python path", resolved)
    if added:
        importlib.invalidate_caches()
    return added
