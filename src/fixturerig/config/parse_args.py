#
# This module contains the code that parses cli arguments into the configuration model
#
# Command line example:
# fixturerig --config some_config.yaml --config another/config.yaml --param key=value
#
# Design decisions:
# - --config is repeatable; each value is a path to a YAML config file. Files
#   are parsed and merged in the order given (see Config.extend in model.py -
#   later files' entries are appended after earlier ones).
# - --param is repeatable and collected as raw "key=value" strings. Where and
#   how a --param override is applied to a fixture or testcase is an open
#   precedence question (see high-level-design skill, "Design Constraints and
#   Open Decisions"). This module does not guess at that; it only validates
#   the "key=value" shape and hands the pairs through unresolved, for the
#   caller (currently main.py) to warn about until precedence is designed.
#

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from fixturerig.config.model import Config, ConfigError


class ArgsError(Exception):
    """Raised for invalid command line arguments."""


@dataclass
class Args:
    """Parsed command line arguments."""

    config_paths: list[Path] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fixturerig", description="Run FixtureRig tests.")
    parser.add_argument(
        "--config",
        dest="config_paths",
        action="append",
        default=[],
        metavar="PATH",
        help="Path to a YAML config file. May be given multiple times; "
        "files are merged in the order given.",
    )
    parser.add_argument(
        "--param",
        dest="params",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a top level parameter. May be given multiple times.",
    )
    return parser


def _split_param(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ArgsError(f"--param must be given as key=value, got {raw!r}")
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        raise ArgsError(f"--param key must not be empty, got {raw!r}")
    return key, value


def read_app_args(argv: list[str] | None = None) -> Args:
    """Parse command line arguments into an Args instance.

    Raises ArgsError (rather than exiting the process) on invalid input, so
    callers such as main.py control how errors are reported.
    """
    parser = build_arg_parser()
    namespace = parser.parse_args(argv)

    if not namespace.config_paths:
        raise ArgsError("At least one --config PATH is required.")

    params: dict[str, str] = {}
    for raw in namespace.params:
        key, value = _split_param(raw)
        if key in params:
            raise ArgsError(f"--param {key!r} given more than once.")
        params[key] = value

    return Args(
        config_paths=[Path(p) for p in namespace.config_paths],
        params=params,
    )


def read_config_from_args(Config, args: Args) -> Config:
    """Parse command line arguments into an Args instance.

    Focus on config model related arguments. This is split to allow calling this from other applications.

    Extracts the params arguments from the args and extends the config model with them.
    Also extends the config model with any tracing and logging related options passed in the command line.
    """
    
