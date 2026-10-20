from fixturerig.base import TestCase
from fixturerig.fixtures.dummy_fixture import DummyFixture
from fixturerig.report import report


class TestCase01(TestCase):
    """Ramps the simulated supply voltage up to `volt` in ten steps.

    Every step is written to the dummy fixture and read back. The test passes
    if every read back value matches its setpoint and the final voltage stays
    within `limit`.
    """

    def __init__(self, dummy: DummyFixture, volt: float, limit: float):
        self.dummy = dummy
        self.volt = volt
        self.limit = limit

    def setup(self) -> None:
        self.dummy.write("voltage", 0.0)

    def test(self) -> bool:
        report().text(f"Ramping the supply to {self.volt} V (limit {self.limit} V)")

        setpoints = [self.volt * step / 10 for step in range(11)]
        readings = []
        for setpoint in setpoints:
            self.dummy.write("voltage", setpoint)
            readings.append(self.dummy.read("voltage"))

        report().chart(
            "Voltage ramp",
            {"setpoint": (list(range(11)), setpoints), "reading": (list(range(11)), readings)},
            x_label="step",
            y_label="V",
        )
        report().table(
            [[step, f"{s:.2f}", f"{r:.2f}"] for step, (s, r) in enumerate(zip(setpoints, readings))],
            headers=["Step", "Setpoint [V]", "Reading [V]"],
            title="Ramp readings",
        )

        report().check(readings == setpoints, "every reading matches its setpoint")
        return report().check(readings[-1] <= self.limit, f"final voltage {readings[-1]:.2f} V <= {self.limit} V")

    def teardown(self) -> None:
        self.dummy.write("voltage", 0.0)
