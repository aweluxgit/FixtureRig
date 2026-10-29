"""Base class for user-defined FixtureRig test generators."""

from __future__ import annotations

from fixturerig.config.model import ConfigEntry


class Generator:
    """Common interface for a generator that adds entries to the config model.

    Subclasses implement :meth:`generate`, which returns the entries -
    ``fixturerig.config.model.TestCase``, ``TestGroup`` or ``Generator``
    objects - to insert at the generator's node. Config parameters are passed
    by name to whichever of ``__init__`` and ``generate`` declare them.

    Generators have no ``setup`` or ``teardown`` hooks.
    """

    def generate(self) -> list[ConfigEntry]:
        """Return the entries to add to the config model."""
        raise NotImplementedError("Generator subclasses must implement generate().")
