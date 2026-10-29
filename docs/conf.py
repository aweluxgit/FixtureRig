# Sphinx configuration for the FixtureRig documentation.
#
# Build locally from the repository root:
#   pip install -e ".[docs]"
#   sphinx-build -W --keep-going -b html docs docs/_build/html

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

# Document the source tree even when the package is not installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

project = "FixtureRig"
author = "Alexander Werth"
copyright = "2026, Alexander Werth"
try:
    release = version("fixturerig")
except PackageNotFoundError:
    release = "0.1.0"
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
]

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
exclude_patterns = ["_build"]

# --- MyST (Markdown) ---------------------------------------------------------------
myst_enable_extensions = ["colon_fence", "deflist", "fieldlist", "substitution"]
myst_heading_anchors = 3
myst_substitutions = {"release": release}

# --- autodoc -----------------------------------------------------------------------
autodoc_member_order = "bysource"
autodoc_default_options = {"members": True, "show-inheritance": True}
autoclass_content = "class"
always_document_param_types = False
typehints_use_signature = False
typehints_use_signature_return = False

# Optional report dependencies are always installed, but mock them so the API
# reference still builds in a minimal environment.
autodoc_mock_imports = ["reportlab", "openpyxl"]

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# Private base classes and docstring phrases that nitpicky mode (-n) misreads as types.
nitpick_ignore = [("py:class", "fixturerig.report.pdf._PdfBase")]
nitpick_ignore_regex = [("py:class", r"True for .*")]

# --- HTML --------------------------------------------------------------------------
html_theme = "furo"
html_title = f"FixtureRig {release}"
html_theme_options = {
    "source_repository": "https://github.com/aweluxgit/FixtureRig",
    "source_branch": "main",
    "source_directory": "docs/",
}
