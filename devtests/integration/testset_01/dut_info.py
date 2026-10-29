from fixturerig.base import Step


class Collect(Step):
    """
    Test spec dut_info 1: a dut_info step runs after the setup steps and
    returns the DUT information as a mapping.
    Expected: group "dut_info: Collect DUT information" with a table of the
    (fake) DUT's serial number, hardware and software version.
    """
    def run(self):
        return {
            "serial_number": "FR-0001",
            "hardware_version": "1.0",
            "software_version": "0.1.0-fake",
        }
