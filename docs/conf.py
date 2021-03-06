#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# wltp documentation build configuration file, created by
# sphinx-quickstart on Thu Jul 31 21:43:57 2014.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

import doctest
import inspect
import importlib
import io
import logging
import os
import re
import subprocess as sbp
import sys

from graphtik import plot
from graphtik.base import func_name, func_sourcelines


projname = "wltp"
mydir = os.path.dirname(__file__)

log = logging.getLogger(__name__)


def _read_project_version() -> str:
    fglobals = {}  # type:ignore
    with io.open(os.path.join(mydir, "..", projname, "_version.py")) as fd:
        exec(fd.read(), fglobals)  # To read __version__
    return fglobals["__version__"]


def _ask_git_version(default: str) -> str:
    try:
        return sbp.check_output(
            "git describe --always".split(), universal_newlines=True
        ).strip()
    except Exception:
        return default


## The full version, including alpha/beta/rc tags
#  for the |release\ replacement
release = os.environ.get("TRAVIS_TAG", _ask_git_version(_read_project_version()))

## The short X.Y version for the |version\ replacement.
version = release


# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
sys.path.insert(0, os.path.abspath("../"))
# sys.path.insert(0, os.path.abspath('../devtools')) # Does not work for scripts :-(


if os.name != "nt":
    autodoc_mock_imports = ["xlwings"]  ## depends on win32


## Make autodoc always includes constructors.
#    From http://stackoverflow.com/a/5599712/548792
#
autodoc_default_options = {
    "private-members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autoclass_content = "both"  # Join class + __init__ docstrings


# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.linkcode",
    "sphinx.ext.autosummary",
    "sphinx.ext.extlinks",
    "sphinx.ext.todo",
    "sphinx.ext.autosectionlabel",
    "matplotlib.sphinxext.plot_directive",
    "sphinx-jsonschema",
    "graphtik.sphinxext",
]


suppress_warnings = [
    "ref.ref",  # Raised by `sphinx-jsonschema` on all $ref.
]
## Ensure literal python code included in doctests,
# for Sphinx-graphtik to work.
doctest_test_doctest_blocks = "default"
# Need functional doctests for graphtik-directive to work ok.
doctest_default_flags = (
    doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS | doctest.REPORT_NDIFF
)

## Plot graphtik SVGs with links to docs.
#
def _make_py_item_url(fn):
    if not inspect.isbuiltin(fn):
        fn_name = func_name(fn, None, mod=1, fqdn=1, human=0)
        if fn_name:
            return f"../code.html#{fn_name}"


plotter = plot.get_active_plotter()
plot.set_active_plotter(
    plotter.with_styles(
        kw_op_label={
            **plotter.default_theme.kw_op_label,
            "op_url": lambda plot_args: _make_py_item_url(plot_args.nx_item),
            "fn_url": lambda plot_args: plot_args.nx_item
            and _make_py_item_url(plot_args.nx_item.fn),
        }
    )
)

autosectionlabel_prefix_document = True


github_slug = "JRCSTU/wltp"
try:
    git_commit = sbp.check_output("git rev-parse HEAD".split()).strip().decode()
    github_uri = f"https://github.com/{github_slug}/blob/{git_commit}/%s.py"
except Exception:
    github_uri = f"https://github.com/{github_slug}/blob/master/%s.py"


def linkcode_resolve(domain, info):
    """Produce URLs to GitHub sources, for ``sphinx.ext.linkcode``"""
    if domain != "py":
        return None
    if not info["module"]:
        return None

    module_name = info["module"]
    item_name = info["fullname"]
    module_path = module_name.replace(".", "/")
    uri = github_uri % module_path  # just the file is too broad

    try:
        item = importlib.import_module(module_name)
    except Exception as ex:
        log.warning(
            "Ignoring failed import while searching lineno of '%s:%s': %s(%s)",
            module_name,
            item_name,
            type(ex).__name__,
            ex,
        )
    else:
        try:
            ## Descend from module towards the item
            #
            for name in item_name.split("."):
                child = getattr(item, name, None)
                if not child:
                    break
                item = child

            source, lineno = func_sourcelines(item, human=0)
            end_lineno = lineno + len(source) - 1
            uri = f"{uri}#L{lineno}-L{end_lineno}"
            return uri
        except TypeError as ex:
            # don't clutter logs, these are mostly non functions.
            assert "module, class, method, function," in str(ex), (ex, item_name)
        except OSError as ex:
            # don't clutter logs, these are mostly non functions or `__new__` specials.
            assert "could not find class definition" in str(
                ex
            ) or "could not get source code" in str(ex), (ex, item_name)
        except Exception as ex:
            log.warning(
                "Ignoring error on while searching lineno of '%s': %s(%s)",
                item,
                type(ex).__name__,
                ex,
            )


#########
## `sphinx-jsonschema` extension
##
jsonschema_options = {
    "lift_title": True,
    "lift_description": True,
    "lift_definitions": True,
    "auto_reference": False,
    "auto_target": False,
}

## PATCH `sphinx-jsonschema`
#  to render the extra `units`` and ``tags`` schema properties
#
def _patched_sphinx_jsonschema_simpletype(self, schema):
    """Render the *extra* ``units`` and ``tags`` schema properties for every object."""
    rows = _original_sphinx_jsonschema_simpletype(self, schema)

    if "units" in schema:
        units = schema["units"]
        units = f"``{units}``"
        rows.append(self._line(self._cell("units"), self._cell(units)))
        del schema["units"]

    if "tags" in schema:
        tags = ", ".join(f"``{tag}``" for tag in schema["tags"])
        rows.append(self._line(self._cell("tags"), self._cell(tags)))
        del schema["tags"]

    return rows


sjs_wide_format = importlib.import_module("sphinx-jsonschema.wide_format")
_original_sphinx_jsonschema_simpletype = sjs_wide_format.WideFormat._simpletype  # type: ignore
sjs_wide_format.WideFormat._simpletype = _patched_sphinx_jsonschema_simpletype  # type: ignore
#
##


# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix of source filenames.
source_suffix = ".rst"

# The encoding of source files.
# source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = "index"

# General information about the project.
project = "wltp"
copyright = "2013-2020, European Commission (JRC), EUPL 1.1+"  # @ReservedAssignment

extlinks = {"issue": ("https://github.com/JRCSTU/wltp/issues/%s", "issue")}
todo_include_todos = True

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
# language = None

# There are two options for replacing |today|: either, you set today to some
# non-false value, then it is used:
# today = ''
# Else, today_fmt is used as the format for a strftime call.
# today_fmt = '%B %d, %Y'

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ["_build", "docs"]

# The reST default role (used for this markup: `text`) to use for all
# documents.
default_role = "obj"

# If true, '()' will be appended to :func: etc. cross-reference text.
# add_function_parentheses = True

# If true, the current module name will be prepended to all description
# unit titles (such as .. function::).
# add_module_names = True

# If true, sectionauthor and moduleauthor directives will be shown in the
# output. They are ignored by default.
# show_authors = False

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "sphinx"

# A list of ignored prefixes for module index sorting.
# modindex_common_prefix = []

# If true, keep warnings as "system message" paragraphs in the built documents.
# keep_warnings = False


# -- Options for HTML output ----------------------------------------------

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
# html_theme_options = {
# }

# Add any paths that contain custom themes here, relative to this directory.
# html_theme_path = []

# The name for this set of Sphinx documents.  If None, it defaults to
# "<project> v<release> documentation".
# html_title = None

# A shorter title for the navigation bar.  Default is the same as html_title.
# html_short_title = None

# The name of an image file (relative to this directory) to place at the top
# of the sidebar.
# html_logo = None

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
# html_favicon = None

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# Add any extra paths that contain custom files (such as robots.txt or
# .htaccess) here, relative to this directory. These files are copied
# directly to the root of the documentation.
# html_extra_path = []

# If not '', a 'Last updated on:' timestamp is inserted at every page bottom,
# using the given strftime format.
html_last_updated_fmt = "%d/%m/%Y %H:%M:%S"

# If true, SmartyPants will be used to convert quotes and dashes to
# typographically correct entities.
# html_use_smartypants = True

# Custom sidebar templates, maps document names to template names.
# html_sidebars = {}

# Additional templates that should be rendered to pages, maps page names to
# template names.
# html_additional_pages = {}

# If false, no module index is generated.
# html_domain_indices = True

# If false, no index is generated.
# html_use_index = True

# If true, the index is split into individual pages for each letter.
# html_split_index = False

# If true, links to the reST sources are added to the pages.
# html_show_sourcelink = True

# If true, "Created using Sphinx" is shown in the HTML footer. Default is True.
# html_show_sphinx = True

# If true, "(C) Copyright ..." is shown in the HTML footer. Default is True.
# html_show_copyright = True

# If true, an OpenSearch description file will be output, and all pages will
# contain a <link> tag referring to it.  The value of this option must be the
# base URL from which the finished HTML is served.
# html_use_opensearch = ''

# This is the file name suffix for HTML files (e.g. ".xhtml").
# html_file_suffix = None

# Output file base name for HTML help builder.
htmlhelp_basename = "wltpdoc"


# -- Options for LaTeX output ---------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #'papersize': 'letterpaper',
    "papersize": "a4paper",
    # The font size ('10pt', '11pt' or '12pt').
    #'pointsize': '10pt',
    # Additional stuff for the LaTeX preamble.
    #'preamble': '',
    "preamble": """
    \\usepackage{amsmath}
""",
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (
        "index",
        "wltp.tex",
        "wltp Documentation",
        "Authors: see '4.5 Development Team' section",
        "manual",
    )
]

# The name of an image file (relative to this directory) to place at the top of
# the title page.
# latex_logo = None

# For "manual" documents, if this is true, then toplevel headings are parts,
# not chapters.
# latex_use_parts = False

# If true, show page references after internal links.
# latex_show_pagerefs = False

# If true, show URL addresses after external links.
# latex_show_urls = False

# Documents to append as an appendix to all manuals.
# latex_appendices = []

# If false, no module index is generated.
# latex_domain_indices = True


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (
        "index",
        "wltp",
        "wltp Documentation",
        ["Authors: see '4.5 Development Team' section"],
        1,
    )
]

# If true, show URL addresses after external links.
# man_show_urls = False


# -- Options for Texinfo output -------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (
        "index",
        "wltp",
        "wltp Documentation",
        "Authors: see '4.5 Development Team' section",
        "wltp",
        "One line description of project.",
        "Miscellaneous",
    )
]

# Documents to append as an appendix to all manuals.
# texinfo_appendices = []

# If false, no module index is generated.
# texinfo_domain_indices = True

# How to display URL addresses: 'footnote', 'no', or 'inline'.
# texinfo_show_urls = 'footnote'

# If true, do not generate a @detailmenu in the "Top" node's menu.
# texinfo_no_detailmenu = False


# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3.7", None),
    "pandas": ("https://pandas-docs.github.io/pandas-docs-travis/", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "jsonschema": ("https://python-jsonschema.readthedocs.io/en/latest/", None),
    "pandalone": ("https://pandalone.readthedocs.io/en/latest/", None),
    "graphtik": ("https://graphtik.readthedocs.io/en/latest/", None),
}
