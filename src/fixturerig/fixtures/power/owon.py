#
# This module holds a fixture for Owon SPE, SPM and P4000 series power supplies
#
# Design decisions:
# - Based on https://pypi.org/project/owon-psu/, which talks SCPI over a
#   serial port. Needs the optional `owon-psu` package
#   (`pip install fixturerig[fixtures]`). It is imported when the fixture is
#   created, so a missing package is reported as a configuration error
#   before any test runs.
# - The library also supports Kiprim DC310S/DC605S devices; open() rejects
#   any device whose identity it doesn't know.
# - The library doesn't wait for set commands to finish, and a Kiprim DC310S
#   silently drops a command sent right after a set command. The fixture
#   keeps `command_delay` between a set command and the next command; 0.2 s
#   was verified on a DC310S.
# - self_test() compares the configured values with the device, so a
#   setting the device didn't take fails the self test instead of a test.
# - setup() applies the configured limits before the setpoints, so a
#   setpoint never exceeds a limit that is about to be lowered, and switches
#   the output off. Tests switch the output on explicitly.
# - disconnect() and teardown() switch the output off, so the DUT is left
#   unpowered also when a test fails. teardown() closes the port even when
#   switching off fails.
# - The library object stays reachable as `psu` for commands this fixture
#   doesn't wrap.
#

from __future__ import annotations

import logging
import time
from typing import Any

from fixturerig.base.fixture import Fixture

logger = logging.getLogger(__name__)


def _require_owon_psu():
    try:
        import owon_psu
    except ImportError as exc:
        raise ImportError(
            "OwonPowerSupply needs the 'owon-psu' package: pip install fixturerig[fixtures]"
        ) from exc
    return owon_psu


class OwonPowerSupply(Fixture):
    """An Owon SPE, SPM or P4000 series power supply on a serial port.

    :param port: serial port, e.g. ``"COM4"`` or ``"/dev/ttyUSB0"``.
    :param timeout: default response timeout in seconds.
    :param voltage: output voltage in V to set in :meth:`setup`.
    :param current: output current in A to set in :meth:`setup`.
    :param voltage_limit: over voltage protection limit in V to set in :meth:`setup`.
    :param current_limit: over current protection limit in A to set in :meth:`setup`.
    :param keylock: lock the front panel keys from :meth:`setup` to :meth:`teardown`.
    :param command_delay: minimum time in seconds between a set command and the next command.
    :param tolerance: allowed difference between a configured value and the device in :meth:`self_test`.

    Values left at ``None`` keep the device's current setting.
    """

    def __init__(
        self,
        port: str,
        timeout: float = 0.5,
        voltage: float | None = None,
        current: float | None = None,
        voltage_limit: float | None = None,
        current_limit: float | None = None,
        keylock: bool = False,
        command_delay: float = 0.2,
        tolerance: float = 0.001,
    ):
        self._owon_psu = _require_owon_psu()
        self.port = port
        self.timeout = timeout
        self.voltage = voltage
        self.current = current
        self.voltage_limit = voltage_limit
        self.current_limit = current_limit
        self.keylock = keylock
        self.command_delay = command_delay
        self.tolerance = tolerance
        self._last_write = 0.0
        #: The ``owon_psu.OwonPSU`` connection, ``None`` while not connected.
        self.psu: Any = None
        #: The ``*IDN?`` response of the connected device.
        self.identity: str | None = None

    # --- device API -------------------------------------------------------------------

    def set_voltage(self, voltage: float) -> None:
        """Set the output voltage in V."""
        self._write("set_voltage", voltage)

    def set_current(self, current: float) -> None:
        """Set the output current in A."""
        self._write("set_current", current)

    def set_voltage_limit(self, voltage: float) -> None:
        """Set the over voltage protection limit in V."""
        self._write("set_voltage_limit", voltage)

    def set_current_limit(self, current: float) -> None:
        """Set the over current protection limit in A."""
        self._write("set_current_limit", current)

    def get_voltage(self) -> float:
        """Return the voltage setpoint in V."""
        return self._connection().get_voltage()

    def get_current(self) -> float:
        """Return the current setpoint in A."""
        return self._connection().get_current()

    def get_voltage_limit(self) -> float:
        """Return the over voltage protection limit in V."""
        return self._connection().get_voltage_limit()

    def get_current_limit(self) -> float:
        """Return the over current protection limit in A."""
        return self._connection().get_current_limit()

    def measure_voltage(self) -> float:
        """Return the measured output voltage in V."""
        return self._connection().measure_voltage()

    def measure_current(self) -> float:
        """Return the measured output current in A."""
        return self._connection().measure_current()

    def set_output(self, enabled: bool) -> None:
        """Switch the output on or off."""
        logger.debug("OwonPowerSupply(%s): output %s", self.port, "on" if enabled else "off")
        self._write("set_output", enabled)

    def output_on(self) -> None:
        """Switch the output on."""
        self.set_output(True)

    def output_off(self) -> None:
        """Switch the output off."""
        self.set_output(False)

    def is_output_on(self) -> bool:
        """Return whether the output is switched on."""
        return self._connection().get_output()

    def set_multimeter_function(self, function: str) -> None:
        """Select the built-in multimeter function (SPM series only).

        :param function: one of ``VOLT:DC``, ``VOLT:AC``, ``CURR:DC``,
            ``CURR:AC``, ``RES``, ``CAP``, ``DIOD`` or ``CONT``.
        """
        self._write("set_multimeter_function", function)

    def measure_multimeter(self) -> float:
        """Return the built-in multimeter reading (SPM series only); ``inf`` for open or overload."""
        return self._connection().measure_multimeter()

    def _connection(self):
        if self.psu is None:
            raise RuntimeError(
                f"OwonPowerSupply on {self.port} is not connected; setup() has not run or teardown() already ran"
            )
        wait = self._last_write + self.command_delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        return self.psu

    def _write(self, command: str, *args) -> None:
        getattr(self._connection(), command)(*args)
        self._last_write = time.monotonic()

    # --- lifecycle --------------------------------------------------------------------

    def setup(self) -> None:
        psu = self._owon_psu.OwonPSU(self.port, default_timeout=self.timeout)
        psu.open()
        self.psu = psu
        self.identity = psu.read_identity()
        logger.info("OwonPowerSupply(%s): connected to %s", self.port, self.identity)
        if self.keylock:
            self._write("set_keylock", True)
        self.output_off()
        if self.voltage_limit is not None:
            self.set_voltage_limit(self.voltage_limit)
        if self.current_limit is not None:
            self.set_current_limit(self.current_limit)
        if self.voltage is not None:
            self.set_voltage(self.voltage)
        if self.current is not None:
            self.set_current(self.current)

    def self_test(self) -> bool:
        checks = [
            ("voltage", self.voltage, self.get_voltage),
            ("current", self.current, self.get_current),
            ("voltage limit", self.voltage_limit, self.get_voltage_limit),
            ("current limit", self.current_limit, self.get_current_limit),
        ]
        ok = True
        for name, configured, read in checks:
            try:
                device = read()
            except Exception:
                logger.exception("OwonPowerSupply(%s): self test could not read the %s", self.port, name)
                return False
            if configured is not None and abs(device - configured) > self.tolerance:
                logger.error("OwonPowerSupply(%s): %s is %s on the device, configured %s", self.port, name, device, configured)
                ok = False
        return ok

    def disconnect(self) -> None:
        if self.psu is not None:
            self.output_off()

    def teardown(self) -> None:
        psu = self.psu
        if psu is None:
            return
        try:
            self.output_off()
            if self.keylock:
                self._write("set_keylock", False)
        finally:
            self.psu = None
            psu.close()
