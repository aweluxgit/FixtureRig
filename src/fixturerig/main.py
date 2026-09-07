#
# Main module for fixturerig
#
# init config module
# Parses arguments
# Parses config files
# launches test generators
# launches tests
# creates test reports
#
# The entire fixturerig module is written in a way that it can be used as a component in another test system.
# The main module is calling these components in a similar way.
#
# Current state: arguments and config files are wired end to end into a
# merged Config. Test generation/execution (fixturerig.core.runner) is not
# implemented yet, so run() stops at returning the parsed Config for a
# future runner (or another host system, per the module docstring above) to
# act on.

from __future__ import annotations

import logging
import sys

from fixturerig.config.model import Config, ConfigError
from fixturerig.config.parse_args import Args, ArgsError, parse_args
from fixturerig.config.parse_yaml import load_config

logger = logging.getLogger("fixturerig")


def run(args: Args) -> Config:
    """Load and merge configuration for the given parsed arguments."""
    config = load_config(args.config_paths)
    logger.info(
        "Loaded %d config file(s): %d fixture(s), %d testcase(s)",
        len(args.config_paths),
        len(config.fixtures()),
        len(config.testcases()),
    )
    if args.params:
        logger.warning(
            "--param override(s) %s were parsed but are not yet applied; "
            "override precedence is not implemented.",
            sorted(args.params),
        )
    return config


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        args = parse_args(argv)
        run(args)
    except ArgsError as exc:
        logger.error("Argument error: %s", exc)
        return 2
    except ConfigError as exc:
        logger.error("Config error: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
