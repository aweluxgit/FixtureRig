#
# This module creates the configured report modules and the run's report stream
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Reporting"
# and "Extension Model"):
#
# - Report modules load like fixtures: `class` is resolved with
#   core.class_loader and the `parametermap` is mapped onto __init__ with
#   core.inheritance, including parameters inherited through **kwargs.
#
# - Report modules have no access to fixtures: a parameter typed as a
#   Fixture is a configuration error.
#
# - Output paths should be given in `parameterpath`, which resolves them
#   relative to the config file (see ConfigPath in config/model.py). A path
#   given as a plain `parametermap` string stays relative to the current
#   working directory.
#
# - ConsoleReport is active by default; see report/console.py for the rule.
#
# - Every problem (unknown class, not a ReportModule, bad parameters, missing
#   optional dependency, invalid values) is raised as a ConfigError before any
#   test runs, naming the config file it came from.
#

from __future__ import annotations

from fixturerig.config.model import Config, ConfigError
from fixturerig.config.model import Report as ReportEntry
from fixturerig.core.class_loader import ClassLoadError, load_class
from fixturerig.core.inheritance import ArgumentMappingError, map_config_to_method_args
from fixturerig.report.console import ConsoleReport
from fixturerig.report.module import ReportModule
from fixturerig.report.stream import ReportStream


def create_report_module(entry: ReportEntry) -> ReportModule:
    """Load, map and instantiate the report module a `report` entry configures."""
    where = f"{entry.source}: " if entry.source else ""
    label = f"report {entry.name!r}" if entry.name else f"report {entry.cls!r}"
    try:
        cls = load_class(entry.cls)
    except ClassLoadError as exc:
        raise ConfigError(f"{where}{label}: {exc}") from exc
    if not issubclass(cls, ReportModule):
        raise ConfigError(f"{where}{label}: {entry.cls!r} is not a subclass of fixturerig.report.ReportModule")
    try:
        kwargs = map_config_to_method_args(entry, cls)
    except ArgumentMappingError as exc:
        raise ConfigError(f"{where}{label}: {exc}") from exc
    try:
        return cls(**kwargs)
    except Exception as exc:
        raise ConfigError(f"{where}{label} could not be created: {exc}") from exc


def build_report_stream(config: Config) -> ReportStream:
    """Create a ReportStream with every configured report module attached.

    A default ConsoleReport is added first unless a ConsoleReport (or
    subclass) is configured.
    """
    modules = [create_report_module(entry) for entry in config.reports()]
    if not any(isinstance(module, ConsoleReport) for module in modules):
        modules.insert(0, ConsoleReport())
    return ReportStream(modules)
