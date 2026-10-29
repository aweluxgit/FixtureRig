# Installation

FixtureRig requires Python 3.10 or newer.

## From a source checkout

```bash
git clone https://github.com/aweluxgit/FixtureRig.git
cd FixtureRig
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The `-e` flag installs FixtureRig in editable mode, so changes to the source take effect without reinstalling. The `dev` extra adds pytest for the framework's own test suite.

## From a wheel

Build a wheel from the repository root (the folder containing `pyproject.toml`):

```bash
python -m pip install build
python -m build                    # writes dist/fixturerig-<version>-py3-none-any.whl
```

Install it into any virtual environment:

```bash
pip install dist/fixturerig-0.1.0-py3-none-any.whl
```

```{tip}
On some Windows systems the interpreter is called `py` instead of `python`. If `pip` is not on `PATH`, call it through the interpreter: `python -m pip ...` or `py -m pip ...`.
```

## As a dependency of another project

Other test systems can declare `fixturerig` as a normal dependency. The package ships a `py.typed` marker, so type checkers and IDEs use its annotations.

## Check the installation

Activating the environment puts the `fixturerig` command on `PATH`:

```bash
fixturerig --version
python -m fixturerig --version     # equivalent, without the launcher
```

## Optional extras

| Extra  | Adds                                        |
|--------|---------------------------------------------|
| `dev`  | pytest, for running FixtureRig's own tests  |
| `docs` | Sphinx and plugins, for building these docs |

The Excel and PDF report modules need `openpyxl` and `reportlab`. Both are installed by default.

Next: {doc}`first-project`.
