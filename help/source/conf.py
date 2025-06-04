# -*- coding: utf-8 -*-
#
# ThemeManager documentation build configuration file, created by
# sphinx-quickstart on Sun Feb 12 17:11:03 2012.
#

import sys, os

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#sys.path.insert(0, os.path.abspath('.'))

# -- General configuration -----------------------------------------------------

extensions = ['sphinx.ext.todo',
              'sphinx.ext.imgmath',
              'sphinx.ext.viewcode']
templates_path = ['_templates']
source_suffix = '.rst'
master_doc = 'index'

# General information about the project.
project = u'ThemeManager'
copyright = u'2025, Antoine BOYER'

version = '1.0'
release = '1.0'

exclude_patterns = []

pygments_style = 'sphinx'

# -- Options for HTML output ---------------------------------------------------

html_theme = 'default'
html_static_path = ['_static']
html_last_updated_fmt = '%b %d, %Y'
html_use_smartypants = True
htmlhelp_basename = 'TemplateClassdoc'

# -- Options for LaTeX output --------------------------------------------------

# The paper size ('letter' or 'a4').
#latex_paper_size = 'letter'

# The font size ('10pt', '11pt' or '12pt').
#latex_font_size = '10pt'

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title, author, documentclass [howto/manual]).
latex_documents = [
  ('index', 'ThemeManager.tex', u'ThemeManager Documentation',
   u'Antoine BOYER', 'manual'),
]

latex_logo = 'icon.png'

latex_preamble = 'Theme Manager est un plugin développé pour QGIS permettant de visualiser la répartition des affichages des couches par thème dans un projet QGIS. Il permet également de créer ou supprimer des thèmes.'

# -- Options for manual page output --------------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ('index', 'TemplateClass', u'ThemeManager Documentation',
     [u'Antoine BOYER'], 1)
]
