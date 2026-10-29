# Contributing

## Development setup

A VS Code dev container is included (`.devcontainer/`). It creates `.venv` and installs the project with the dev extras. Without it:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,docs]"
```

## Tests

```bash
pytest                                        # unit tests
devtests/integration/run_integration_tests.sh # integration test sets (Windows: .bat)
```

The `FixtureRig: demo test_02` launch configuration in `.vscode/launch.json` runs the demo under the debugger.

## Documentation

The docs are built with [Sphinx](https://www.sphinx-doc.org/) from Markdown pages ([MyST](https://myst-parser.readthedocs.io/)) in `docs/` and from the docstrings in `src/`.

```bash
sphinx-build -W --keep-going -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. Warnings are treated as errors, as in CI.

The `docs` workflow in `.github/workflows/docs.yml` builds the docs for every push and pull request and publishes `main` to <https://aweluxgit.github.io/FixtureRig/>.

The pages follow the [Diátaxis](https://diataxis.fr/) structure:

| Folder | Kind | Answers |
|--------|------|---------|
| `getting-started/` | Tutorials | "Teach me" |
| `how-to/` | How-to guides | "How do I ...?" |
| `reference/` | Reference | "What exactly is ...?" |
| `explanation/` | Explanation | "Why ...?" |

When you change behaviour, update the matching reference page and the docstrings in the same change.

### Docstrings

Docstrings use reStructuredText with Sphinx roles, so the API reference cross-links them:

```python
def set_voltage(self, volts: float) -> None:
    """Set the output voltage.

    :param volts: target voltage; must not exceed :attr:`max_voltage`.
    :raises ValueError: if `volts` is above the limit.
    """
```

Put types in the signature, not in the docstring; they are added to the docs automatically.

## Building a wheel

```bash
python -m pip install build
python -m build
```
