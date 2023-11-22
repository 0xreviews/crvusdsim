# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys
import crvusdsim

# Insert crvusdsim path into the system.
sys.path.insert(0, os.path.abspath(".."))

project = 'crvusdsim'
copyright = '2023, 0xreviews'
author = '0xreviews'
# The short X.Y version.
version = crvusdsim.__version__
# The full version, including alpha/beta/rc tags.
release = crvusdsim.__version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = []

templates_path = ['_templates']
exclude_patterns = []

language = 'python'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "pallets_sphinx_themes",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx.ext.mathjax",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

autodoc_class_signature = "separated"
# Napoleon settings
napoleon_include_init_with_doc = True

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "flask"
html_static_path = ["_static"]

mathjax3_config = {
    "tex": {"inlineMath": [["$", "$"], ["\\(", "\\)"]]},
}

# Custom sidebar templates, maps document names to template names.
html_sidebars = {
    "index": ["sidebarintro.html", "sourcelink.html", "searchbox.html"],
    "**": [
        "sidebarlogo.html",
        "localtoc.html",
        "relations.html",
        "sourcelink.html",
        "searchbox.html",
    ],
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
}
