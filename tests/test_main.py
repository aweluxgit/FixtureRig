from pathlib import Path

import pytest

from fixturerig.config.parse_args import read_args
from fixturerig.main import main, run


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_run_loads_and_merges_configured_files(tmp_path):
    first = _write(tmp_path, "first.yaml", "- fixture:\n    name: can\n    class: pkg.Can\n")
    second = _write(
        tmp_path,
        "second.yaml",
        "- testcase:\n    name: voltage_limit\n    class: pkg.VoltageLimitTest\n",
    )
    args = read_args(["--config", str(first), "--config", str(second)])

    config = run(args)

    assert [entry.name for entry in config.entries] == ["can", "voltage_limit"]


def test_main_returns_zero_on_success(tmp_path):
    config_path = _write(tmp_path, "config.yaml", "- fixture:\n    name: can\n    class: pkg.Can\n")

    assert main(["--config", str(config_path)]) == 0


def test_main_returns_two_on_args_error():
    assert main([]) == 2


def test_main_returns_one_on_config_error(tmp_path):
    bad_config = _write(tmp_path, "bad.yaml", "- widget:\n    name: x\n")

    assert main(["--config", str(bad_config)]) == 1
