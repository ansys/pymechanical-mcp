# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Sphinx documentation configuration file."""

from datetime import datetime
import os
from pathlib import Path
import re
import sys

from ansys_sphinx_theme import ansys_favicon, get_version_match, pyansys_logo_black

# Add package source directory for autodoc/version imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def _read_project_version() -> str:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to determine project version from pyproject.toml")
    return match.group(1)


__version__ = _read_project_version()

# Project information
project = "pymechanical-mcp"
copyright = f"(c) {datetime.now().year} ANSYS, Inc. All rights reserved"
author = "ANSYS, Inc."
release = version = __version__
cname = os.getenv("DOCUMENTATION_CNAME", "mechanical-mcp.docs.pyansys.com")
switcher_version = get_version_match(__version__)

REPOSITORY_NAME = "pymechanical-mcp"
USERNAME = "ansys"
BRANCH = "main"

# Select desired logo, theme, and declare the html title
html_logo = pyansys_logo_black
html_theme = "ansys_sphinx_theme"
html_short_title = html_title = "PyMechanical-MCP"

# Favicon
html_favicon = ansys_favicon

# specify the location of your github repository
html_theme_options = {
    "github_url": f"https://github.com/{USERNAME}/{REPOSITORY_NAME}",
    "show_prev_next": False,
    "show_breadcrumbs": True,
    "collapse_navigation": True,
    "use_edit_page_button": True,
    "additional_breadcrumbs": [
        ("PyAnsys", "https://docs.pyansys.com/"),
    ],
    "icon_links": [
        {
            "name": "Support",
            "url": f"https://github.com/{USERNAME}/{REPOSITORY_NAME}/discussions",
            "icon": "fa fa-comment fa-fw",
        },
    ],
    "switcher": {
        "json_url": f"https://{cname}/versions.json",
        "version_match": switcher_version,
    },
    "check_switcher": False,
}

html_context = {
    "display_github": True,
    "github_user": USERNAME,
    "github_repo": REPOSITORY_NAME,
    "github_version": BRANCH,
    "doc_path": "doc/source",
}

# Sphinx extensions
extensions = [
    "numpydoc",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
]

autodoc_mock_imports = [
    "ansys.mechanical.core",
]
autosummary_mock_imports = autodoc_mock_imports

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "ansys-mechanical-core": ("https://mechanical.docs.pyansys.com/version/stable/", None),
}

# numpydoc configuration
numpydoc_show_class_members = False
numpydoc_xref_param_type = True
autosectionlabel_prefix_document = True

numpydoc_validate = False
numpydoc_validation_checks = set()

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix(es) of source filenames.
source_suffix = ".rst"

# The master toctree document.
master_doc = "index"

language = "en"

exclude_patterns = [
    "_build",
    "links.rst",
]

suppress_warnings = [
    "toc.not_included",
    "toc.not_readable",
    "design.fa-build",
]

# make rst_epilog a variable, so you can add other epilog parts to it
rst_epilog = ""
# Read link all targets from file
with Path("links.rst").open() as f:
    rst_epilog += f.read()

linkcheck_exclude_documents = ["404", "changelog"]
linkcheck_ignore = [
    "https://github.com/ansys/pymechanical-mcp/*",
    "https://modelcontextprotocol.io/*",
    "https://www.sphinx-doc.org/*",
]

linkcheck_allowed_redirect = [
    r"https://tox.wiki/",
]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

latex_documents = [
    (
        master_doc,
        f"{project}-Documentation-{__version__}.tex",
        f"{project} Documentation",
        author,
        "manual",
    ),
]
