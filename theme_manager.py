# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ThemeManager
                                 A QGIS plugin
 Manage the layers of many map themes at once.
                              -------------------
        begin                : 2025-05-22
        copyright            : (C) 2025 by Antoine BOYER
        email                : theme.manager.qgis.plugin@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator
from qgis.PyQt.QtWidgets import QAction, QPushButton
from qgis.core import QgsSettings

from .theme_guard import ThemeGuard
from .utils import PLUGIN_DIR, message_level, plugin_icon, tr


class ThemeManager:
    def __init__(self, iface):
        self.iface = iface
        self.translator = None
        self.action = None
        self.dlg = None
        self.guard = None
        self._install_translator()
        self.menu = tr("&Theme Manager")

    def _install_translator(self):
        locale = QgsSettings().value("locale/userLocale", "") or QLocale().name()
        lang = (locale or "en")[0:2]
        path = os.path.join(PLUGIN_DIR, "i18n", "theme_manager_{}.qm".format(lang))
        if os.path.exists(path):
            self.translator = QTranslator()
            if self.translator.load(path):
                QCoreApplication.installTranslator(self.translator)
            else:
                self.translator = None

    def initGui(self):
        self.action = QAction(plugin_icon(), tr("Theme Manager"), self.iface.mainWindow())
        self.action.setStatusTip(tr("Manage the layers of all map themes"))
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.menu, self.action)

        # Works in the background, even when the window is closed.
        self.guard = ThemeGuard(self.iface.mainWindow())
        self.guard.restorableLayersAdded.connect(self._offer_restore)
        self.guard.groupsRepaired.connect(self._notify_groups_repaired)

    def unload(self):
        if self.dlg is not None:
            self.dlg.cleanup()
            self.dlg.close()
            self.dlg.deleteLater()
            self.dlg = None
        if self.guard is not None:
            self.guard.unload()
            self.guard.deleteLater()
            self.guard = None
        if self.action is not None:
            self.iface.removePluginMenu(self.menu, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

    def run(self):
        if self.dlg is None:
            from .theme_manager_dialog import ThemeManagerDialog
            self.dlg = ThemeManagerDialog(self.iface, self.guard)
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    # ------------------------------------------------------------------ #
    #  Guard notifications (message bar, never modal)
    # ------------------------------------------------------------------ #
    def _offer_restore(self, matches):
        orphans = self.guard.orphans()
        matches = [(layer, orphan_id) for layer, orphan_id in matches if orphan_id in orphans]
        if not matches:
            return
        theme_count = len({theme for _layer, orphan_id in matches for theme in orphans[orphan_id].get("themes", {})})
        if len(matches) == 1:
            text = tr("Layer «{layer}» was used by {count} map theme(s) before it was removed.").format(
                layer=matches[0][0].name(), count=theme_count)
        else:
            text = tr("{layers} added layers were used by {count} map theme(s) before they were removed.").format(
                layers=len(matches), count=theme_count)
        bar = self.iface.messageBar()
        widget = bar.createMessage(tr("Theme Manager"), text)
        button = QPushButton(tr("Restore in the themes"), widget)

        def restore():
            self.guard.restore_layers({orphan_id: layer for layer, orphan_id in matches})
            bar.popWidget(widget)
            bar.pushSuccess(tr("Theme Manager"), tr("Layers restored in the map themes."))

        button.clicked.connect(restore)
        widget.layout().addWidget(button)
        bar.pushWidget(widget, message_level("Info"), 0)

    def _notify_groups_repaired(self, mapping):
        text = tr("Map themes updated after renaming or moving {count} group(s).").format(count=len(mapping))
        self.iface.messageBar().pushMessage(tr("Theme Manager"), text, message_level("Info"), 4)
