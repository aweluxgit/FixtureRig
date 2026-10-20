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
from fixturerig.config.parse_args import Args, ArgsError, read_config_from_args, read_app_args
from fixturerig.config.parse_yaml import read_config_files
from fixturerig.core.class_loader import add_python_paths
from fixturerig.core.runner import run_tests
from fixturerig.report.loader import build_report_stream
from fixturerig.report.stream import ReportStream

logger = logging.getLogger("fixturerig")



def config_summary(config, args: Args) -> Config:
    """Load and merge configuration for the given parsed arguments."""
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



def prepare_reports(config: Config) -> ReportStream:
    """Create the report stream with every configured report module attached."""
    return build_report_stream(config)


def finalize_reports(report_stream: ReportStream) -> None:
    """Let every report module finish its output (e.g. write its files)."""
    report_stream.close()


def phase_run_test(config, report_stream: ReportStream | None = None):
    run_tests(config, report_stream)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = Config(entries=[])
        args = read_app_args(argv)
        read_config_from_args(config, args)
        read_config_files(config, args.config_paths)
        config_summary(config, args)
        add_python_paths(config)
        report_stream = prepare_reports(config)
        try:
            # run_generators(config)
            run_tests(config, report_stream)
        finally:
            finalize_reports(report_stream)

    except ArgsError as exc:
        logger.error("Argument error: %s", exc)
        return 2
    except ConfigError as exc:
        logger.error("Config error: %s", exc)
        return 1
    return 0



    config = phase_configuration(argv)
    #phase_run_generators(config)
    phase_run_test(config)
    #phase_finalize_reports(config)


if __name__ == "__main__":
    sys.exit(main())
