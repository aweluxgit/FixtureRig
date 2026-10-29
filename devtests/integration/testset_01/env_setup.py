import hashlib
from pathlib import Path

from fixturerig.base import Step
from fixturerig.report import report


class PrepareEnv(Step):
    """
    Test spec env_setup 1: an env_setup step without parameters runs before
    the DUT information gathering and everything else.
    Expected: group "env_setup: Prepare environment" with one text line.
    """
    def run(self):
        report.text("Environment prepared")


class FlashFirmware(Step):
    """
    Test spec env_setup 2: a step gets a parameterpath resolved relative to
    the config file as a Path and returns information, which is reported as
    a table.
    Expected: group "env_setup: Flash Firmware" with a table holding the
    firmware file name, size and SHA-256 checksum. If the file is missing the
    step fails and every test is skipped.
    """
    def run(self, path: Path):
        image = path.read_bytes()
        report.text(f"Flashing {path.name} ({len(image)} bytes)")
        return {
            "file": path.name,
            "size": len(image),
            "sha256": hashlib.sha256(image).hexdigest(),
        }
