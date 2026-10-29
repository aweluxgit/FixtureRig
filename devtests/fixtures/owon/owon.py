#
# Hardware tests for the Owon power supply fixture
#
# Design decisions:
# - These tests drive a real device; run them with
#   `python -m fixturerig --config devtests/fixtures/owon/owon.yaml`
#   after setting the serial port in owon.yaml.
# - The output must be open (no load connected): the measured voltage is
#   compared against the setpoint, and the output is switched on.
# - Voltages stay at or below the configured limits, so a misconfigured
#   rig is caught by the device's protection instead of a test.
#

import time

from fixturerig.base import TestCase
from fixturerig.fixtures.power.owon import OwonPowerSupply
from fixturerig.report import report


def _wait_for_voltage(psu: OwonPowerSupply, condition, settle_time: float) -> float:
    """Poll the measured voltage until `condition` holds or `settle_time` passes; return the last reading."""
    deadline = time.monotonic() + settle_time
    while True:
        measured = psu.measure_voltage()
        if condition(measured) or time.monotonic() >= deadline:
            return measured
        time.sleep(0.1)


class Identity(TestCase):
    """
    The fixture connected to a supported device and reports its identity.
    """

    def test(self, psu: OwonPowerSupply):
        report.text(f"Port: {psu.port}")
        report.text(f"Identity: {psu.identity}")
        return report.check(bool(psu.identity), "device returned an identity")


class ConfiguredSettings(TestCase):
    """
    setup() applied the configured setpoints and limits, and left the output off.
    """

    def test(self, psu: OwonPowerSupply, tolerance: float):
        rows = [
            ["voltage", psu.voltage, psu.get_voltage(), "V"],
            ["current", psu.current, psu.get_current(), "A"],
            ["voltage limit", psu.voltage_limit, psu.get_voltage_limit(), "V"],
            ["current limit", psu.current_limit, psu.get_current_limit(), "A"],
        ]
        report.table(rows, headers=["Setting", "Configured", "Device", "Unit"], title="Settings after setup")
        ok = True
        for name, configured, device, _ in rows:
            if configured is not None:
                ok &= report.check(abs(device - configured) <= tolerance, f"{name}: {device} matches {configured}")
        ok &= report.check(not psu.is_output_on(), "output is off after setup")
        return ok


class SetpointReadback(TestCase):
    """
    Setpoints written through the fixture are read back from the device.
    """

    def test(self, psu: OwonPowerSupply, voltages: list[float], currents: list[float], tolerance: float):
        rows = []
        ok = True
        for voltage in voltages:
            psu.set_voltage(voltage)
            readback = psu.get_voltage()
            rows.append(["voltage", voltage, readback])
            ok &= report.check(abs(readback - voltage) <= tolerance, f"voltage {voltage} V read back as {readback} V")
        for current in currents:
            psu.set_current(current)
            readback = psu.get_current()
            rows.append(["current", current, readback])
            ok &= report.check(abs(readback - current) <= tolerance, f"current {current} A read back as {readback} A")
        report.table(rows, headers=["Setpoint", "Written", "Read"], title="Setpoint readback")
        return ok

    def teardown(self, psu: OwonPowerSupply):
        # Restore the configured setpoints for the following tests.
        psu.set_voltage(psu.voltage)
        psu.set_current(psu.current)


class OutputSwitching(TestCase):
    """
    Switching the output on brings the measured voltage to the setpoint;
    switching it off brings it back down.
    """

    def test(self, psu: OwonPowerSupply, measure_tolerance: float, settle_time: float, off_threshold: float):
        setpoint = psu.get_voltage()

        psu.output_on()
        ok = report.check(psu.is_output_on(), "output reports on")
        measured = _wait_for_voltage(psu, lambda u: abs(u - setpoint) <= measure_tolerance, settle_time)
        ok &= report.check(
            abs(measured - setpoint) <= measure_tolerance, f"output on: measured {measured} V, setpoint {setpoint} V"
        )
        report.text(f"Measured current with open output: {psu.measure_current()} A")

        psu.output_off()
        ok &= report.check(not psu.is_output_on(), "output reports off")
        measured = _wait_for_voltage(psu, lambda u: u <= off_threshold, settle_time)
        ok &= report.check(measured <= off_threshold, f"output off: measured {measured} V <= {off_threshold} V")
        return ok

    def teardown(self, psu: OwonPowerSupply):
        psu.output_off()


class VoltageSweep(TestCase):
    """
    The measured output voltage follows a sweep of setpoints.
    """

    def test(self, psu: OwonPowerSupply, voltages: list[float], measure_tolerance: float, settle_time: float):
        measured = []
        ok = True
        psu.output_on()
        for voltage in voltages:
            psu.set_voltage(voltage)
            reading = _wait_for_voltage(psu, lambda u: abs(u - voltage) <= measure_tolerance, settle_time)
            measured.append(reading)
            ok &= report.check(abs(reading - voltage) <= measure_tolerance, f"setpoint {voltage} V measured {reading} V")
        psu.output_off()

        report.table(
            [[voltage, reading, reading - voltage] for voltage, reading in zip(voltages, measured)],
            headers=["Setpoint [V]", "Measured [V]", "Error [V]"],
            title="Voltage sweep",
        )
        report.chart(
            "Voltage sweep",
            {"setpoint": (voltages, voltages), "measured": (voltages, measured)},
            x_label="setpoint [V]",
            y_label="V",
        )
        return ok

    def teardown(self, psu: OwonPowerSupply):
        psu.output_off()
        psu.set_voltage(psu.voltage)
