"""Base class for user-defined lifecycle steps (env_setup, dut_info, dut_shutdown)."""

from __future__ import annotations

from typing import Any, Mapping


class Step:
    """Common interface for one step of a lifecycle stage around the tests.

    Subclasses implement :meth:`run`. Config parameters are passed by name to
    whichever of ``__init__`` and ``run`` declare them. A parameter with a
    :class:`~fixturerig.base.Fixture` type hint is a reference to a configured
    fixture, as for test cases; the fixture is started before ``run`` and
    stopped after it.

    ``run`` may return a mapping of information, e.g. the DUT's serial number
    and software version in a ``dut_info`` step; it is reported as a table.
    Raise an exception to make the step fail.

    Steps have no ``setup`` or ``teardown`` hooks.
    """

    def run(self) -> Mapping[str, Any] | None:
        """Perform the step, optionally returning information to report."""
        raise NotImplementedError("Step subclasses must implement run().")
