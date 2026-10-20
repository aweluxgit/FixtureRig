#
# This module holds a hardware free fixture for demos and framework tests
#
# Design decisions:
# - DummyFixture simulates a device as a set of named numeric registers that
#   tests write and read back. It needs no hardware, so demo projects and
#   framework tests can exercise the full fixture lifecycle anywhere.
# - Every lifecycle hook is recorded in `calls`, so tests can check the
#   order the runner drives fixtures in.
# - `self_test_ok: false` makes the self test fail, to demonstrate how the
#   runner skips the tests that depend on a broken fixture.
#

from __future__ import annotations

import logging

from fixturerig.base.fixture import Fixture

logger = logging.getLogger(__name__)


class DummyFixture(Fixture):
    """A simulated device with named numeric registers.

    :param values: initial register values, e.g. ``{"voltage": 0.0}``.
    :param self_test_ok: result of :meth:`self_test`.
    """

    def __init__(self, values: dict[str, float] | None = None, self_test_ok: bool = True):
        self.values: dict[str, float] = {name: float(value) for name, value in (values or {}).items()}
        self.self_test_ok = self_test_ok
        self.calls: list[str] = []
        self.connected = False

    # --- device API -------------------------------------------------------------------

    def write(self, name: str, value: float) -> None:
        """Set register `name` to `value`."""
        self._require_connection()
        self.values[name] = float(value)

    def read(self, name: str) -> float:
        """Return the value of register `name`."""
        self._require_connection()
        try:
            return self.values[name]
        except KeyError:
            known = ", ".join(sorted(self.values)) or "none"
            raise KeyError(f"DummyFixture has no register {name!r} (known: {known})") from None

    def _require_connection(self) -> None:
        if not self.connected:
            raise RuntimeError("DummyFixture is not connected; setup() has not run or teardown() already ran")

    # --- lifecycle --------------------------------------------------------------------

    def _record(self, hook: str) -> None:
        self.calls.append(hook)
        logger.debug("DummyFixture.%s()", hook)

    def setup(self) -> None:
        self._record("setup")
        self.connected = True

    def self_test(self) -> bool:
        self._record("self_test")
        return self.self_test_ok

    def start(self) -> None:
        self._record("start")

    def stop(self) -> None:
        self._record("stop")

    def lazy_stop(self) -> None:
        self._record("lazy_stop")

    def disconnect(self) -> None:
        self._record("disconnect")

    def teardown(self) -> None:
        self._record("teardown")
        self.connected = False
