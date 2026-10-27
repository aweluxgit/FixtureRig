from fixturerig.base import TestCase
from fixturerig.fixtures.dummy_fixture import DummyFixture
from fixturerig.report import Chart, Series, Table, Text, report


class TestCase01(TestCase):
    """
    Test spec 1
    """
    def test(self, param1: int, param2: float, param3: str):
        report.text(f"Assert that type hint based conversions work for int, float, string")
        ok = report.check(isinstance(param1, int), f"Instance of param1 is {type(param1)} with value {param1}")
        ok &= report.check(isinstance(param2, float), f"Instance of param2 is {type(param2)} with value {param2}")
        ok &= report.check(isinstance(param3, str), f"Instance of param3 is {type(param3)} with value {param3}")
        return ok


class TestCase0101(TestCase):
    """
    Test spec 1.1: line, scatter and bar charts
    """
    def test(self, param2: float):
        report.text(f"Check that charts are working")
        report.check(isinstance(param2, float), f"Instance of param2 is {type(param2)} with value {param2}")
        times = [0.1 * step for step in range(11)]
        ramp = [param2 * t for t in times]
        report.chart("Ramp", {"U": (times, ramp), "U/2": (times, [u / 2 for u in ramp])}, x_label="s", y_label="V")
        report.chart(Chart("Samples", [Series("U", times, ramp)], "s", "V", kind="scatter"))
        report.chart("Bars", {"count": ([1, 2, 3], [3.0, 1.0, 2.0])}, x_label="bin", y_label="n", kind="bar")
        return report.passed("charts reported")

class TestCase0102(TestCase):
    """
    Test spec 1.2: simple, titled and complex tables
    """
    def test(self, dummy: DummyFixture, param2: float):
        report.text(f"Check that tables are working")
        report.check(isinstance(param2, float), f"Instance of param2 is {type(param2)} with value {param2}")

        report.table([["a", 1], ["b", 2.5], ["c", True], ["d", None]])
        report.table([["U", 4.93, "V"], ["I", 0.21, "A"]], headers=["Signal", "Value", "Unit"], title="Titled table")

        setpoints = [0.0, param2, 2 * param2]
        readings = []
        for setpoint in setpoints:
            dummy.write("voltage", setpoint)
            readings.append(dummy.read("voltage"))
        report.table(
            [[setpoint, reading] for setpoint, reading in zip(setpoints, readings)],
            headers=["Setpoint", "Reading"],
            title="Dummy register readback",
        )
        report.check(readings == setpoints, "every reading matches its setpoint")

        nested = Table([["x", 1], ["y", 2]], headers=["Key", "Value"])
        chart = Chart("Readback", [Series("voltage", list(range(len(readings))), readings)], "step", "V")
        report.table(
            [["nested table", nested], ["chart", chart], ["text", Text("a text element")]],
            headers=["Kind", "Element"],
            title="Complex table",
        )
        return report.passed("tables reported")
