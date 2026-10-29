from pathlib import Path

import pytest

from fixturerig.config.model import Config
from fixturerig.config.parse_args import read_app_args
from fixturerig.config.parse_yaml import read_config_files
from fixturerig.main import main


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_args_config_paths_load_and_merge_in_order(tmp_path):
    first = _write(tmp_path, "first.yaml", "- fixture:\n    name: can\n    class: pkg.Can\n")
    second = _write(
        tmp_path,
        "second.yaml",
        "- testcase:\n    name: voltage_limit\n    class: pkg.VoltageLimitTest\n",
    )
    args = read_app_args(["--config", str(first), "--config", str(second)])

    config = read_config_files(Config(entries=[]), args.config_paths)

    assert [entry.name for entry in config.entries] == ["can", "voltage_limit"]


def test_main_returns_zero_on_success(tmp_path):
    config_path = _write(tmp_path, "config.yaml", "- fixture:\n    name: can\n    class: pkg.Can\n")

    assert main(["--config", str(config_path)]) == 0


def test_main_returns_two_on_args_error():
    assert main([]) == 2


def test_main_returns_one_on_config_error(tmp_path):
    bad_config = _write(tmp_path, "bad.yaml", "- widget:\n    name: x\n")

    assert main(["--config", str(bad_config)]) == 1


def test_main_interactive_lets_a_test_exception_through(tmp_path):
    (tmp_path / "crashing_tests.py").write_text(
        "from fixturerig.base import TestCase\n\n"
        "class Crashes(TestCase):\n"
        "    def test(self):\n"
        "        raise ZeroDivisionError('interactive')\n",
        encoding="utf-8",
    )
    config_path = _write(
        tmp_path,
        "config.yaml",
        "- pythonpath: .\n- testcase:\n    name: crash\n    class: crashing_tests.Crashes\n",
    )

    assert main(["--config", str(config_path)]) == 0
    with pytest.raises(ZeroDivisionError, match="interactive"):
        main(["--config", str(config_path), "--interactive"])
