from fixturerig.base import Generator, TestCase
from fixturerig.config.model import TestCase as TestCaseEntry
from fixturerig.config.model import TestGroup
from fixturerig.report import report


class GeneratedTest(TestCase):
    """
    Test created by the generators of group 4: checks that the generated
    parameter arrives converted to the type hint.
    Expected verdict: passed
    """
    def test(self, value: int):
        report.text(f"Generated test got value {value!r}")
        return report.check(isinstance(value, int), f"Instance of value is {type(value)}")


class Generator0401(Generator):
    """
    Test spec 4.1: generate() takes `count` from the config and creates that
    many tests. They are placed in a group named after the generator.
    Expected: group "4.1: generator that adds a few tests" with tests
    4.1.1 to 4.1.<count>, all passed.
    """
    def generate(self, count: int):
        return [
            TestCaseEntry(
                name=f"4.1.{i}: expect passed: generated test",
                cls="tests.testcases_04.GeneratedTest",
                params={"value": i},
            )
            for i in range(1, count + 1)
        ]


class Generator0402(Generator):
    """
    Test spec 4.2: with create_group false the generated entries are added
    directly to the generator node. Creates a test and a group with a test,
    with a prefix from __init__ and a value from generate().
    Expected: test 4.2.1 and group 4.2.2 directly in group 4, all passed.
    """
    def __init__(self, prefix: str):
        self.prefix = prefix

    def generate(self, value: int):
        return [
            TestCaseEntry(
                name=f"{self.prefix}.1: expect passed: generated test",
                cls="tests.testcases_04.GeneratedTest",
                params={"value": value},
            ),
            TestGroup(
                name=f"group {self.prefix}.2 generated group",
                entries=[
                    TestCaseEntry(
                        name=f"{self.prefix}.2.1: expect passed: generated test in generated group",
                        cls="tests.testcases_04.GeneratedTest",
                        params={"value": str(value)},
                    )
                ],
            ),
        ]
