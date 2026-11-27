# -*- coding: utf-8 -*-
"""
Small helpers shared by every module of the plugin: translation, icons,
settings and Qt enum access that works with both PyQt5 (QGIS 3) and
PyQt6 (QGIS 4).
"""

import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import Qgis, QgsApplication, QgsSettings

PLUGIN_DIR = os.path.dirname(__file__)
SETTINGS_PREFIX = "theme_manager/"
TR_CONTEXT = "ThemeManager"


def tr(text):
    """Translate a user visible string (single context for the whole plugin)."""
    return QCoreApplication.translate(TR_CONTEXT, text)


def theme_icon(name):
    """Return a QGIS theme icon, e.g. theme_icon("mActionFileOpen.svg")."""
    return QgsApplication.getThemeIcon("/" + name)


def plugin_icon():
    return QIcon(os.path.join(PLUGIN_DIR, "icon.png"))


def setting(key, default=None, value_type=None):
    settings = QgsSettings()
    if value_type is None:
        return settings.value(SETTINGS_PREFIX + key, default)
    return settings.value(SETTINGS_PREFIX + key, default, type=value_type)


def set_setting(key, value):
    QgsSettings().setValue(SETTINGS_PREFIX + key, value)


def message_level(name):
    """Qgis.MessageLevel member that works on QGIS 3.22+ and QGIS 4."""
    enum = getattr(Qgis, "MessageLevel", None)
    if enum is not None and hasattr(enum, name):
        return getattr(enum, name)
    return getattr(Qgis, name)


def plugin_version():
    try:
        with open(os.path.join(PLUGIN_DIR, "metadata.txt"), "r", encoding="utf-8") as metadata_file:
            for line in metadata_file:
                if line.startswith("version="):
                    return line.strip().split("=", 1)[1]
    except (OSError, UnicodeError):
        pass
    return ""
