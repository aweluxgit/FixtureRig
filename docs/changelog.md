# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added

- Lifecycle steps: `env_setup`, `dut_info` and `dut_shutdown` entries with the {class}`~fixturerig.base.Step` base class.
- `--interactive` mode for debugging tests in an IDE.
- This documentation.

## 0.1.0

First development release.

### Added

- YAML config parsing with strict validation, `pythonpath`, `parameterpath` and `fixturemap`.
- Inheritance-aware mapping of config parameters onto constructor and method arguments.
- Ordered runner with fixture lifecycle, autoloaded fixtures, test groups and generators.
- Report stream with console, JSON, HTML, Allure, Excel, PDF and PDF test specification modules.
- `fixturerig` command and wheel build.
