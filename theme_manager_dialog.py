# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ThemeManagerDialog
                                 A QGIS plugin
 Manage the layers of many map themes at once.
                             -------------------
        begin                : 2025-05-22
        copyright            : (C) 2025 by Antoine BOYER
        email                : theme.manager.qgis.plugin@gmail.com
 ***************************************************************************/

Main window of the plugin.

Left: the list of map themes (filterable, multi-selection).
Right: the project layer tree, drawn like the QGIS "Layers" panel.
  * one theme selected   -> check boxes next to each layer/group, exactly
                            like in the Layers panel, for that theme;
  * several selected     -> one check box column per theme, to compare and
                            edit them side by side.
"""

import datetime
import os
import re

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QItemSelectionModel, QSize, Qt, QTimer
from qgis.PyQt.QtGui import QIcon, QPalette, QPixmap
from qgis.core import QgsLayerTree, QgsProject
from qgis.gui import QgsFilterLineEdit

try:
    from qgis.core import QgsIconUtils
except ImportError:  # QGIS < 3.20
    QgsIconUtils = None

from . import theme_model as tm
from . import theme_xml
from .theme_dialogs import ExportDialog, ImportDialog, MappingDialog, ask_theme_name
from .utils import plugin_icon, plugin_version, set_setting, setting, theme_icon, tr

ROLE = Qt.ItemDataRole.UserRole
CHECKED = Qt.CheckState.Checked
UNCHECKED = Qt.CheckState.Unchecked

SHOW_ALL, SHOW_VISIBLE, SHOW_HIDDEN, SHOW_DIFF = range(4)
KEEP, FORGET, REMOVE = "", "__forget__", "__remove__"


def natural_key(text):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text)]


class ThemeItem(QtWidgets.QTreeWidgetItem):
    """Theme list item: natural sort on the name, numeric sort on the layer count."""

    def __lt__(self, other):
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        if column == 1:
            return (self.data(1, ROLE) or 0) < (other.data(1, ROLE) or 0)
        return natural_key(self.text(0)) < natural_key(other.text(0))


class ThemeManagerDialog(QtWidgets.QDialog):

    def __init__(self, iface, guard, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.guard = guard
        self.project = QgsProject.instance()
        self.record_cache = {}       # records of layers unchecked during the session (keeps styles)
        self._updating = False       # True while check boxes are set programmatically
        self._filtering = False
        self._names = {}             # key -> layer name shown in the tree
        self._items = {}             # key ("L:<layer id>" / "G:<group path>") -> QTreeWidgetItem
        self._columns = []           # themes shown in the layer tree
        self._views = {}             # theme -> ThemeView
        self._active = set()         # themes identical to the current map
        self._expanded = None        # keys of expanded groups/layers (None: take them from QGIS)
        self._pending = set()
        self._collection = None
        self._connections = []

        self.setWindowTitle(tr("Theme Manager"))
        self.setWindowIcon(plugin_icon())
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setSizeGripEnabled(True)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(60)
        self._refresh_timer.timeout.connect(self._process_pending)

        self._build_ui()
        self._connect_project()
        self._restore_settings()
        self.refresh_all()

    # ================================================================== #
    #  UI
    # ================================================================== #
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ---- toolbar ---------------------------------------------------- #
        self.toolbar = QtWidgets.QToolBar(self)
        self.toolbar.setIconSize(QSize(20, 20))
        self.act_new = self._action("symbologyAdd.svg", tr("New theme from the current map"), self.create_theme, "Ctrl+N")
        self.act_duplicate = self._action("mActionDuplicateLayer.svg", tr("Duplicate theme"), self.duplicate_theme)
        self.act_delete = self._action("symbologyRemove.svg", tr("Delete selected themes"), self.delete_themes)
        self.toolbar.addSeparator()
        self.act_replace = self._action("mActionRefresh.svg", tr("Replace theme with the current map"), self.replace_theme)
        self.act_apply = self._action("mActionShowAllLayers.svg", tr("Apply to map"), self.apply_current_theme)
        self.toolbar.addSeparator()
        self.act_import = self._action("mActionSharingImport.svg", tr("Import themes from a file…"), self.import_themes)
        self.act_export = self._action("mActionSharingExport.svg", tr("Export themes to a file…"), self.export_themes)
        spacer = QtWidgets.QWidget(self)
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)
        self.act_repair = self._action("mIconWarning.svg", tr("Repair themes…"), self.repair_themes)
        for action in (self.act_apply, self.act_repair):
            self.toolbar.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        layout.addWidget(self.toolbar)
        blank = QPixmap(16, 16)
        blank.fill(Qt.GlobalColor.transparent)
        self._blank_icon = QIcon(blank)

        # ---- left: themes ---------------------------------------------- #
        left = QtWidgets.QWidget(self)
        left.setMinimumWidth(220)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.theme_filter = QgsFilterLineEdit(left)
        self.theme_filter.setShowSearchIcon(True)
        self.theme_filter.setPlaceholderText(tr("Filter themes…"))
        self.theme_filter.textChanged.connect(self._filter_theme_list)
        left_layout.addWidget(self.theme_filter)

        self.theme_list = QtWidgets.QTreeWidget(left)
        self.theme_list.setColumnCount(2)
        self.theme_list.setHeaderLabels([tr("Theme"), tr("Layers")])
        self.theme_list.headerItem().setToolTip(1, tr("Number of layers visible in the theme"))
        self.theme_list.setRootIsDecorated(False)
        self.theme_list.setUniformRowHeights(True)
        self.theme_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.theme_list.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed)
        self.theme_list.setSortingEnabled(True)
        self.theme_list.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.theme_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header = self.theme_list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.theme_list.itemSelectionChanged.connect(self._on_theme_selection_changed)
        self.theme_list.itemChanged.connect(self._on_theme_item_changed)
        self.theme_list.itemDoubleClicked.connect(lambda item, _col: self.apply_theme(item.data(0, ROLE)))
        self.theme_list.customContextMenuRequested.connect(self._theme_context_menu)
        left_layout.addWidget(self.theme_list, 1)
        # Shortcuts limited to the theme list (Del must not delete themes while typing in a filter).
        self.act_rename = QtWidgets.QAction(tr("Rename"), self.theme_list)
        self.act_rename.setShortcut("F2")
        self.act_rename.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.act_rename.triggered.connect(self.rename_current_theme)
        self.theme_list.addAction(self.act_rename)
        delete_shortcut = QtWidgets.QAction(self.theme_list)
        delete_shortcut.setShortcut("Del")
        delete_shortcut.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.triggered.connect(self.delete_themes)
        self.theme_list.addAction(delete_shortcut)

        hint = QtWidgets.QLabel(tr("Ctrl/Shift + click to compare several themes. Double-click to apply."), left)
        hint.setWordWrap(True)
        hint.setEnabled(False)
        left_layout.addWidget(hint)

        # ---- right: layer tree ----------------------------------------- #
        right = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        row = QtWidgets.QHBoxLayout()
        self.layer_filter = QgsFilterLineEdit(right)
        self.layer_filter.setShowSearchIcon(True)
        self.layer_filter.setPlaceholderText(tr("Filter layers…"))
        self.layer_filter.textChanged.connect(self._apply_layer_filter)
        row.addWidget(self.layer_filter, 1)
        self.show_mode = QtWidgets.QComboBox(right)
        self.show_mode.addItem(tr("All layers"), SHOW_ALL)
        self.show_mode.addItem(tr("Visible in theme"), SHOW_VISIBLE)
        self.show_mode.addItem(tr("Hidden in theme"), SHOW_HIDDEN)
        self.show_mode.addItem(tr("Differences between themes"), SHOW_DIFF)
        self.show_mode.currentIndexChanged.connect(self._apply_layer_filter)
        row.addWidget(self.show_mode)
        for icon, tip, slot in (("mActionExpandTree.svg", tr("Expand all"), self._expand_all),
                                ("mActionCollapseTree.svg", tr("Collapse all"), self._collapse_all)):
            button = QtWidgets.QToolButton(right)
            button.setIcon(theme_icon(icon))
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(slot)
            row.addWidget(button)
        right_layout.addLayout(row)

        self.layer_tree = QtWidgets.QTreeWidget(right)
        self.layer_tree.setUniformRowHeights(True)
        self.layer_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.layer_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.layer_tree.setExpandsOnDoubleClick(True)
        self.layer_tree.header().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.layer_tree.header().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layer_tree.header().setMinimumSectionSize(28)
        self.layer_tree.itemChanged.connect(self._on_layer_item_changed)
        self.layer_tree.itemExpanded.connect(lambda item: self._remember_expanded(item, True))
        self.layer_tree.itemCollapsed.connect(lambda item: self._remember_expanded(item, False))
        self.layer_tree.itemDoubleClicked.connect(self._on_layer_double_clicked)
        self.layer_tree.customContextMenuRequested.connect(self._layer_context_menu)
        self.layer_tree.header().customContextMenuRequested.connect(self._header_context_menu)
        self.layer_tree.installEventFilter(self)
        right_layout.addWidget(self.layer_tree, 1)

        self.status = QtWidgets.QLabel(right)
        self.status.setWordWrap(True)
        right_layout.addWidget(self.status)

        self.splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter, 1)

        # ---- bottom ---------------------------------------------------- #
        bottom = QtWidgets.QHBoxLayout()
        self.auto_apply = QtWidgets.QCheckBox(tr("Apply the selected theme to the map"), self)
        self.auto_apply.setToolTip(tr("Show each theme on the map canvas as soon as it is selected in the list."))
        self.auto_apply.toggled.connect(self._on_auto_apply_toggled)
        bottom.addWidget(self.auto_apply)
        bottom.addStretch(1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.close)
        bottom.addWidget(buttons)
        layout.addLayout(bottom)

    def _action(self, icon, text, slot, shortcut=None):
        action = QtWidgets.QAction(theme_icon(icon), text, self)
        action.setToolTip(text + (" ({})".format(shortcut) if shortcut else ""))
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        self.toolbar.addAction(action)
        return action

    # ================================================================== #
    #  Settings
    # ================================================================== #
    def _restore_settings(self):
        geometry = setting("dialog/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1000, 650)
        splitter = setting("dialog/splitter")
        if splitter is None or not self.splitter.restoreState(splitter):
            self.splitter.setSizes([300, max(500, self.width() - 300)])
        self.auto_apply.setChecked(setting("dialog/auto_apply", False, bool))

    def _save_settings(self):
        set_setting("dialog/geometry", self.saveGeometry())
        set_setting("dialog/splitter", self.splitter.saveState())

    def _on_auto_apply_toggled(self, checked):
        set_setting("dialog/auto_apply", checked)
        if checked:
            theme = self.current_theme()
            if theme and len(self.selected_themes()) == 1:
                self.apply_theme(theme)

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending:
            self._process_pending()

    # ================================================================== #
    #  Project signals
    # ================================================================== #
    def _connect_project(self):
        project = self.project
        root = project.layerTreeRoot()
        self._connections = [
            (root.addedChildren, lambda *a: self._schedule("tree")),
            (root.removedChildren, lambda *a: self._schedule("tree")),
            (root.nameChanged, lambda *a: self._schedule("tree")),
            (root.visibilityChanged, lambda *a: self._schedule("active")),
            (project.readProject, lambda *a: self._on_project_reset()),
            (project.cleared, self._on_project_reset),
            (self.guard.issuesChanged, lambda: self._schedule("themes")),
        ]
        if hasattr(project, "mapThemeCollectionChanged"):
            self._connections.append((project.mapThemeCollectionChanged, self._connect_collection))
        for signal, slot in self._connections:
            signal.connect(slot)
        self._connect_collection()

    def _connect_collection(self):
        self._disconnect_collection()
        self._collection = self.project.mapThemeCollection()
        self._collection.mapThemesChanged.connect(self._on_themes_changed)
        self._collection.mapThemeChanged.connect(self._on_themes_changed)
        self._collection.mapThemeRenamed.connect(self._on_theme_renamed)
        self._schedule("themes")

    def _disconnect_collection(self):
        collection, self._collection = self._collection, None
        if collection is None:
            return
        for signal, slot in ((collection.mapThemesChanged, self._on_themes_changed),
                             (collection.mapThemeChanged, self._on_themes_changed),
                             (collection.mapThemeRenamed, self._on_theme_renamed)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def cleanup(self):
        """Disconnect from the project (called when the plugin is unloaded)."""
        self._refresh_timer.stop()
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._connections = []
        self._disconnect_collection()

    def _on_project_reset(self):
        self.record_cache.clear()
        self._expanded = None
        self._schedule("themes", "tree")

    def _on_themes_changed(self, *args):
        self._schedule("themes")

    def _on_theme_renamed(self, old_name, new_name):
        for item in self._theme_items().values():
            if item.data(0, ROLE) == old_name:
                self._updating = True
                item.setData(0, ROLE, new_name)
                item.setText(0, new_name)
                self._updating = False
        self.record_cache = {(new_name if theme == old_name else theme, layer_id): record
                             for (theme, layer_id), record in self.record_cache.items()}
        self._schedule("themes", "tree")

    def _schedule(self, *kinds):
        self._pending.update(kinds)
        if self.isVisible():
            self._refresh_timer.start()

    def _process_pending(self):
        pending, self._pending = self._pending, set()
        if "themes" in pending:
            self._refresh_theme_list()
        if "tree" in pending or "columns" in pending:
            self._rebuild_layer_tree()
        elif "themes" in pending:
            self._update_checks()
        elif "active" in pending:
            self._update_active()

    def refresh_all(self):
        self._pending.clear()
        self._refresh_theme_list()
        self._rebuild_layer_tree()

    # ================================================================== #
    #  Theme list
    # ================================================================== #
    def _theme_items(self):
        return {self.theme_list.topLevelItem(i).data(0, ROLE): self.theme_list.topLevelItem(i)
                for i in range(self.theme_list.topLevelItemCount())}

    def all_themes(self):
        return list(self.project.mapThemeCollection().mapThemes())

    def selected_themes(self):
        """Selected themes, in the order of the list."""
        items = self.theme_list.selectedItems()
        items.sort(key=lambda item: self.theme_list.indexOfTopLevelItem(item))
        return [item.data(0, ROLE) for item in items]

    def current_theme(self):
        item = self.theme_list.currentItem()
        if item is not None and item.isSelected():
            return item.data(0, ROLE)
        selected = self.selected_themes()
        return selected[0] if selected else None

    def _refresh_theme_list(self):
        collection = self.project.mapThemeCollection()
        themes = self.all_themes()
        self._active = tm.active_themes(self.iface, self.project)
        orphans = self.guard.orphans()
        stale = self.guard.stale_groups()

        self._updating = True
        self.theme_list.setSortingEnabled(False)
        selection_before = self.selected_themes()
        items = self._theme_items()
        for name, item in items.items():
            if name not in themes:
                self.theme_list.takeTopLevelItem(self.theme_list.indexOfTopLevelItem(item))
        for theme in themes:
            item = items.get(theme)
            if item is None:
                item = ThemeItem(self.theme_list, [theme, ""])
                item.setData(0, ROLE, theme)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            view = tm.ThemeView(collection.mapThemeState(theme))
            count = view.visible_count()
            item.setText(1, str(count))
            item.setData(1, ROLE, count)
            removed = [info.get("name", layer_id) for layer_id, info in orphans.items() if theme in info.get("themes", {})]
            missing_groups = [path for path, names in stale.items() if theme in names]
            tips = [theme]
            if theme in self._active:
                tips.append(tr("Currently shown on the map."))
            if removed:
                tips.append(tr("Layers removed from the project: {names}").format(names=", ".join(sorted(removed))))
            if missing_groups:
                tips.append(tr("Groups not found in the layer tree: {names}").format(names=", ".join(sorted(missing_groups))))
            item.setToolTip(0, "\n".join(tips))
            if removed or missing_groups:
                item.setIcon(0, theme_icon("mIconWarning.svg"))
            elif theme in self._active:
                item.setIcon(0, theme_icon("mIconSuccess.svg"))
            else:
                item.setIcon(0, self._blank_icon)
            font = item.font(0)
            font.setBold(theme in self._active)
            item.setFont(0, font)
        self.theme_list.setSortingEnabled(True)
        self._filter_theme_list(self.theme_filter.text())

        if not self.theme_list.selectedItems() and self.theme_list.topLevelItemCount():
            # Select the theme shown on the map, else the first one.
            target = next((item for name, item in self._theme_items().items() if name in self._active), None)
            target = target or self.theme_list.topLevelItem(0)
            self.theme_list.setCurrentItem(target)
        self._updating = False
        if self.selected_themes() != selection_before:
            self._on_theme_selection_changed()
        self._update_actions()

    def _filter_theme_list(self, text):
        text = (text or "").casefold()
        for item in self._theme_items().values():
            item.setHidden(bool(text) and text not in item.text(0).casefold())

    def _update_actions(self):
        selected = self.selected_themes()
        has_themes = bool(self.theme_list.topLevelItemCount())
        self.act_duplicate.setEnabled(len(selected) == 1)
        self.act_delete.setEnabled(bool(selected))
        self.act_replace.setEnabled(len(selected) == 1)
        self.act_apply.setEnabled(bool(selected))
        self.act_rename.setEnabled(len(selected) == 1)
        self.act_export.setEnabled(has_themes)
        issues = self.guard.issue_count()
        self.act_repair.setVisible(issues > 0)
        self.act_repair.setText(tr("Repair themes ({count})…").format(count=issues))

    def _on_theme_selection_changed(self):
        if self._updating:
            return
        self._update_actions()
        self._rebuild_layer_tree()
        selected = self.selected_themes()
        if self.auto_apply.isChecked() and len(selected) == 1:
            self.apply_theme(selected[0])

    def _on_theme_item_changed(self, item, column):
        """Inline rename (F2)."""
        if self._updating or column != 0:
            return
        old_name = item.data(0, ROLE)
        new_name = item.text(0).strip()
        if new_name == old_name:
            return
        error = None
        if not new_name:
            error = tr("Please enter a theme name.")
        elif new_name in self.all_themes():
            error = tr("A theme with this name already exists.")
        if error:
            self._updating = True
            item.setText(0, old_name)
            self._updating = False
            QtWidgets.QMessageBox.warning(self, tr("Rename theme"), error)
            return
        self.project.mapThemeCollection().renameMapTheme(old_name, new_name)

    def _theme_context_menu(self, pos):
        item = self.theme_list.itemAt(pos)
        menu = QtWidgets.QMenu(self)
        selected = self.selected_themes()
        if item is not None and selected:
            menu.addAction(self.act_apply)
            menu.addAction(self.act_rename)
            menu.addAction(self.act_duplicate)
            menu.addAction(self.act_replace)
            menu.addSeparator()
            menu.addAction(self.act_export)
            menu.addSeparator()
            menu.addAction(self.act_delete)
        else:
            menu.addAction(self.act_new)
            menu.addAction(self.act_import)
        menu.exec(self.theme_list.viewport().mapToGlobal(pos))

    # ================================================================== #
    #  Layer tree
    # ================================================================== #
    def _single(self):
        return len(self._columns) <= 1

    def _column_of(self, index):
        """Tree column of the index-th displayed theme."""
        return 0 if self._single() else index + 1

    def _theme_at(self, column):
        if not self._columns:
            return None
        if self._single():
            return self._columns[0] if column == 0 else None
        index = column - 1
        return self._columns[index] if 0 <= index < len(self._columns) else None

    def _rebuild_layer_tree(self):
        tree = self.layer_tree
        self._columns = [theme for theme in self.selected_themes() if theme in self.all_themes()]
        single = self._single()
        scroll = tree.verticalScrollBar().value()
        selected_keys = {item.data(0, ROLE) for item in tree.selectedItems()}
        current = tree.currentItem()
        current_key = current.data(0, ROLE) if current is not None else None

        self._updating = True
        tree.setUpdatesEnabled(False)
        tree.clear()
        self._items = {}
        self._names = {}
        if single:
            tree.setColumnCount(1)
            tree.setHeaderLabels([self._columns[0] if self._columns else tr("Layers")])
            tree.header().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        else:
            tree.setColumnCount(len(self._columns) + 1)
            tree.setHeaderLabels([tr("Layer")] + self._columns)
            tree.header().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
            header_item = tree.headerItem()
            header_item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Interactive)
            for index, theme in enumerate(self._columns, start=1):
                header_item.setToolTip(index, tr("{theme}\nRight-click for more actions").format(theme=theme))
                tree.header().setSectionResizeMode(index, QtWidgets.QHeaderView.ResizeMode.Interactive)
                width = min(160, max(56, tree.fontMetrics().horizontalAdvance(theme) + 18))
                tree.setColumnWidth(index, width)
            tree.setColumnWidth(0, max(260, tree.columnWidth(0)))
        tree.header().setStretchLastSection(single)

        root = self.project.layerTreeRoot()
        first_build = self._expanded is None
        if first_build:
            self._expanded = set()
        self._add_children(tree.invisibleRootItem(), root, "", first_build)
        if single and self._columns:
            self._add_missing_section(self._columns[0])

        for key, item in self._items.items():
            if key in self._expanded:
                item.setExpanded(True)
            if key in selected_keys:
                item.setSelected(True)
            if key == current_key:
                tree.setCurrentItem(item, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._updating = False
        self._update_checks()
        tree.setUpdatesEnabled(True)
        tree.verticalScrollBar().setValue(scroll)

    def _add_children(self, parent_item, node, path, first_build):
        checkable = bool(self._columns)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if checkable:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        for child in node.children():
            if QgsLayerTree.isGroup(child):
                child_path = "{}/{}".format(path, child.name()) if path else child.name()
                key = "G:" + child_path
                item = QtWidgets.QTreeWidgetItem(parent_item, [child.name()])
                item.setIcon(0, theme_icon("mActionFolder.svg"))
                item.setToolTip(0, child_path)
                item.setData(0, ROLE, key)
                item.setFlags(flags)
                self._items[key] = item
                if first_build and child.isExpanded():
                    self._expanded.add(key)
                self._add_children(item, child, child_path, first_build)
            elif QgsLayerTree.isLayer(child):
                layer = child.layer()
                key = "L:" + child.layerId()
                item = QtWidgets.QTreeWidgetItem(parent_item, [child.name()])
                item.setData(0, ROLE, key)
                self._names[key] = child.name()
                if layer is None:
                    item.setIcon(0, theme_icon("mIconWarning.svg"))
                    item.setToolTip(0, tr("Layer not available"))
                    item.setFlags(Qt.ItemFlag.ItemIsSelectable)
                else:
                    if QgsIconUtils is not None:
                        item.setIcon(0, QgsIconUtils.iconForLayer(layer))
                    item.setToolTip(0, "{}\n{}".format(layer.name(), tm.safe_source(layer)))
                    item.setFlags(flags)
                self._items[key] = item

    def _add_missing_section(self, theme):
        """Show what the theme references but the project no longer has."""
        removed = [(layer_id, info) for layer_id, info in self.guard.orphans().items() if theme in info.get("themes", {})]
        groups = [path for path, names in self.guard.stale_groups().items() if theme in names]
        if not removed and not groups:
            return
        top = QtWidgets.QTreeWidgetItem(self.layer_tree, [tr("Missing from the project ({count}) — double-click to repair").format(
            count=len(removed) + len(groups))])
        top.setIcon(0, theme_icon("mIconWarning.svg"))
        top.setData(0, ROLE, "X:")
        top.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = top.font(0)
        font.setItalic(True)
        top.setFont(0, font)
        for path in sorted(groups):
            item = QtWidgets.QTreeWidgetItem(top, [path])
            item.setIcon(0, theme_icon("mActionFolder.svg"))
            item.setToolTip(0, tr("Group renamed, moved or removed"))
            item.setData(0, ROLE, "X:")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        for _layer_id, info in sorted(removed, key=lambda entry: entry[1].get("name", "")):
            item = QtWidgets.QTreeWidgetItem(top, [info.get("name", "")])
            item.setIcon(0, theme_icon("mActionRemoveLayer.svg"))
            item.setToolTip(0, tr("Layer removed from the project\n{source}").format(source=info.get("source", "")))
            item.setData(0, ROLE, "X:")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        top.setExpanded(True)

    def _update_checks(self):
        """Read the themes and update every check box (no rebuild)."""
        collection = self.project.mapThemeCollection()
        existing = set(collection.mapThemes())
        if any(theme not in existing for theme in self._columns):
            self._schedule("columns")
            return
        self._views = {theme: tm.ThemeView(collection.mapThemeState(theme)) for theme in self._columns}
        self._updating = True
        disabled = self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        normal = self.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text)
        for key, item in self._items.items():
            if not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                continue
            for index, theme in enumerate(self._columns):
                item.setCheckState(self._column_of(index), CHECKED if self._is_checked(theme, key) else UNCHECKED)
            if self._single() and self._columns:
                # Grey out what is hidden by an unchecked parent group, like QGIS does.
                view = self._views[self._columns[0]]
                hidden = False
                parent = item.parent()
                while parent is not None:
                    parent_key = parent.data(0, ROLE)
                    if parent_key.startswith("G:") and not view.group_checked(parent_key[2:]):
                        hidden = True
                        break
                    parent = parent.parent()
                item.setForeground(0, disabled if hidden else normal)
                if key.startswith("L:"):
                    layer = self.project.mapLayer(key[2:])
                    style = view.style(key[2:]) if view.layer_visible(key[2:]) else ""
                    name = self._names.get(key, item.text(0))
                    if style and layer is not None and len(tm.layer_styles(layer)) > 1:
                        name = "{}  [{}]".format(name, style)
                    item.setText(0, name)
        self._updating = False
        self._apply_layer_filter()
        self._update_status()
        self._update_active()

    def _is_checked(self, theme, key):
        view = self._views.get(theme)
        if view is None:
            return False
        if key.startswith("G:"):
            return view.group_checked(key[2:])
        return view.layer_visible(key[2:])

    def _update_active(self):
        active = tm.active_themes(self.iface, self.project)
        if active != self._active:
            self._active = active
            self._schedule("themes")

    def _update_status(self):
        layers = [key for key in self._items if key.startswith("L:")]
        if not self.theme_list.topLevelItemCount():
            text = tr("This project has no map theme yet. Set up the layers in the Layers panel, "
                      "then click \"New theme from the current map\".")
        elif not self._columns:
            text = tr("Select a theme in the list.")
        elif self._single():
            theme = self._columns[0]
            visible = sum(1 for key in layers if self._is_checked(theme, key))
            text = tr("«{theme}»: {visible} of {total} layers visible.").format(theme=theme, visible=visible, total=len(layers))
            if theme in self._active:
                text += " " + tr("Shown on the map.")
            text += " " + tr("Ctrl+click a group check box to switch all its children.")
        else:
            differences = sum(1 for key in layers if len({self._is_checked(t, key) for t in self._columns}) > 1)
            text = tr("Comparing {count} themes: {diff} layers differ. Right-click a column header for column actions.").format(
                count=len(self._columns), diff=differences)
        self.status.setText(text)

    def _remember_expanded(self, item, expanded):
        if self._updating or self._filtering or self._expanded is None:
            return
        key = item.data(0, ROLE)
        if expanded:
            self._expanded.add(key)
        else:
            self._expanded.discard(key)

    def _expand_all(self):
        self.layer_tree.expandAll()

    def _collapse_all(self):
        self.layer_tree.collapseAll()

    def _apply_layer_filter(self, *args):
        text = self.layer_filter.text().casefold()
        mode = self.show_mode.currentData()
        if mode == SHOW_DIFF and self._single():
            mode = SHOW_ALL
        self._filtering = True

        def layer_matches(key):
            states = [self._is_checked(theme, key) for theme in self._columns]
            if mode == SHOW_VISIBLE:
                return any(states)
            if mode == SHOW_HIDDEN:
                return not all(states) if states else True
            if mode == SHOW_DIFF:
                return len(set(states)) > 1
            return True

        def visit(item, ancestor_matched):
            key = item.data(0, ROLE) or ""
            text_ok = ancestor_matched or not text or text in item.text(0).casefold()
            children = [visit(item.child(i), text_ok) for i in range(item.childCount())]
            if key.startswith("L:"):
                visible = text_ok and layer_matches(key)
            elif key.startswith("G:"):
                visible = any(children) or (text_ok and (mode == SHOW_ALL or layer_matches(key)))
            else:
                visible = True
            item.setHidden(not visible)
            if key.startswith("G:"):
                if (text or mode != SHOW_ALL) and any(children):
                    item.setExpanded(True)
                elif not text and mode == SHOW_ALL:
                    item.setExpanded(key in (self._expanded or ()))
            return visible

        root = self.layer_tree.invisibleRootItem()
        for i in range(root.childCount()):
            visit(root.child(i), False)
        self._filtering = False

    # ---- editing -------------------------------------------------------- #
    def _on_layer_item_changed(self, item, column):
        if self._updating:
            return
        theme = self._theme_at(column)
        if theme is None:
            return
        checked = item.checkState(column) == CHECKED
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            targets = [item] + self._descendants(item)
        elif item.isSelected() and len(self.layer_tree.selectedItems()) > 1:
            targets = self.layer_tree.selectedItems()
        else:
            targets = [item]
        self.set_checked(targets, [theme], checked)

    def _descendants(self, item):
        result = []
        for i in range(item.childCount()):
            child = item.child(i)
            result.append(child)
            result.extend(self._descendants(child))
        return result

    def _ancestors(self, item):
        result = []
        parent = item.parent()
        while parent is not None:
            result.append(parent)
            parent = parent.parent()
        return result

    def set_checked(self, items, themes, checked):
        """Show/hide layers and groups (tree items) in the given themes."""
        was_active = self._active & set(themes)
        edit = tm.ThemeEdit(self.project, self.record_cache)
        all_paths = tm.all_group_paths(self.project.layerTreeRoot())
        for theme in themes:
            for item in items:
                key = item.data(0, ROLE) or ""
                if not item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    continue
                if key.startswith("G:"):
                    edit.set_group_checked(theme, key[2:], checked, all_paths)
                elif key.startswith("L:"):
                    layer = self.project.mapLayer(key[2:])
                    if layer is not None:
                        edit.set_layer_visible(theme, layer, checked)
        self._commit(edit, was_active)

    def _commit(self, edit, was_active):
        modified = edit.commit()
        self._pending.discard("themes")
        self._update_checks()
        self._refresh_theme_list()
        # Keep the map in sync when the edited theme is the one displayed.
        for theme in modified:
            if theme in was_active:
                self.apply_theme(theme)
                break

    def eventFilter(self, obj, event):
        if obj is self.layer_tree and event.type() == event.Type.KeyPress and event.key() == Qt.Key.Key_Space:
            self._toggle_selected(self.layer_tree.currentColumn())
            return True
        return super().eventFilter(obj, event)

    def _toggle_selected(self, column):
        items = [item for item in self.layer_tree.selectedItems() if item.flags() & Qt.ItemFlag.ItemIsUserCheckable]
        if not items or not self._columns:
            return
        theme = self._theme_at(column) or self._theme_at(self._column_of(0))
        current = self.layer_tree.currentItem() or items[0]
        checked = not self._is_checked(theme, current.data(0, ROLE) or "")
        self.set_checked(items, [theme], checked)

    def _on_layer_double_clicked(self, item, _column):
        if (item.data(0, ROLE) or "") == "X:":
            self.repair_themes()

    def _layer_context_menu(self, pos):
        item = self.layer_tree.itemAt(pos)
        if not self._columns:
            return
        menu = QtWidgets.QMenu(self)
        items = [i for i in self.layer_tree.selectedItems() if i.flags() & Qt.ItemFlag.ItemIsUserCheckable]
        if item is not None and item not in items and item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            items = [item]
        column = self.layer_tree.columnAt(pos.x())
        column_theme = self._theme_at(column) if not self._single() else None
        themes = [column_theme] if column_theme else list(self._columns)
        if len(themes) == 1:
            show_text = tr("Show in «{theme}»").format(theme=themes[0])
            hide_text = tr("Hide in «{theme}»").format(theme=themes[0])
        else:
            show_text, hide_text = tr("Show in all compared themes"), tr("Hide in all compared themes")

        if items:
            menu.addAction(theme_icon("mActionShowSelectedLayers.svg"), show_text,
                           lambda: self.set_checked(items, themes, True))
            menu.addAction(theme_icon("mActionHideAllLayers.svg"), hide_text,
                           lambda: self.set_checked(items, themes, False))
            if column_theme and len(self._columns) > 1:
                menu.addAction(tr("Show in all compared themes"), lambda: self.set_checked(items, list(self._columns), True))
                menu.addAction(tr("Hide in all compared themes"), lambda: self.set_checked(items, list(self._columns), False))
            if any((i.data(0, ROLE) or "").startswith("G:") for i in items):
                menu.addSeparator()
                with_children = items + [d for i in items for d in self._descendants(i)]
                menu.addAction(tr("Check and all children (Ctrl+click)"), lambda: self.set_checked(with_children, themes, True))
                menu.addAction(tr("Uncheck and all children (Ctrl+click)"), lambda: self.set_checked(with_children, themes, False))
            with_parents = items + [a for i in items for a in self._ancestors(i)]
            menu.addAction(tr("Check and all parents"), lambda: self.set_checked(with_parents, themes, True))

            if self._single() and len(items) == 1 and (items[0].data(0, ROLE) or "").startswith("L:"):
                self._add_style_menu(menu, items[0], self._columns[0])
        menu.addSeparator()
        menu.addAction(theme_icon("mActionExpandTree.svg"), tr("Expand all"), self._expand_all)
        menu.addAction(theme_icon("mActionCollapseTree.svg"), tr("Collapse all"), self._collapse_all)
        menu.exec(self.layer_tree.viewport().mapToGlobal(pos))

    def _add_style_menu(self, menu, item, theme):
        layer = self.project.mapLayer(item.data(0, ROLE)[2:])
        if layer is None:
            return
        styles = tm.layer_styles(layer)
        if len(styles) < 2 or not self._is_checked(theme, item.data(0, ROLE)):
            return
        current = self._views[theme].style(layer.id())
        submenu = menu.addMenu(tr("Style in this theme"))
        for style in styles:
            action = submenu.addAction(style)
            action.setCheckable(True)
            action.setChecked(style == current)
            action.triggered.connect(lambda _checked=False, s=style: self._set_style(layer, theme, s))

    def _set_style(self, layer, theme, style):
        edit = tm.ThemeEdit(self.project, self.record_cache)
        edit.set_layer_style(theme, layer, style)
        self._commit(edit, self._active & {theme})
        self._rebuild_layer_tree()

    def _header_context_menu(self, pos):
        column = self.layer_tree.header().logicalIndexAt(pos)
        theme = self._theme_at(column) if not self._single() else (self._columns[0] if self._columns else None)
        if theme is None:
            return
        items = [item for item in self._items.values() if item.flags() & Qt.ItemFlag.ItemIsUserCheckable]
        visible_items = [item for item in items if not item.isHidden()]
        menu = QtWidgets.QMenu(self)
        menu.addAction(tr("Check all in «{theme}»").format(theme=theme), lambda: self.set_checked(visible_items, [theme], True))
        menu.addAction(tr("Uncheck all in «{theme}»").format(theme=theme), lambda: self.set_checked(visible_items, [theme], False))
        menu.addAction(tr("Invert in «{theme}»").format(theme=theme), lambda: self._invert(visible_items, theme))
        menu.addSeparator()
        menu.addAction(tr("Apply «{theme}» to the map").format(theme=theme), lambda: self.apply_theme(theme))
        if not self._single():
            menu.addAction(tr("Edit «{theme}» alone").format(theme=theme), lambda: self.select_themes([theme]))
        menu.exec(self.layer_tree.header().mapToGlobal(pos))

    def _invert(self, items, theme):
        to_check = [item for item in items if not self._is_checked(theme, item.data(0, ROLE))]
        to_uncheck = [item for item in items if self._is_checked(theme, item.data(0, ROLE))]
        was_active = self._active & {theme}
        edit = tm.ThemeEdit(self.project, self.record_cache)
        all_paths = tm.all_group_paths(self.project.layerTreeRoot())
        for items_, checked in ((to_check, True), (to_uncheck, False)):
            for item in items_:
                key = item.data(0, ROLE)
                if key.startswith("G:"):
                    edit.set_group_checked(theme, key[2:], checked, all_paths)
                else:
                    layer = self.project.mapLayer(key[2:])
                    if layer is not None:
                        edit.set_layer_visible(theme, layer, checked)
        self._commit(edit, was_active)

    def select_themes(self, themes):
        items = self._theme_items()
        self._updating = True
        self.theme_list.clearSelection()
        first = None
        for theme in themes:
            item = items.get(theme)
            if item is not None:
                item.setSelected(True)
                first = first or item
        if first is not None:
            self.theme_list.setCurrentItem(first, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
            self.theme_list.scrollToItem(first)
        self._updating = False
        self._on_theme_selection_changed()

    # ================================================================== #
    #  Theme operations
    # ================================================================== #
    def apply_theme(self, theme):
        if theme and theme in self.all_themes():
            tm.apply_theme(self.iface, theme, self.project)
            self._active = {theme}
            self._schedule("themes")

    def apply_current_theme(self):
        self.apply_theme(self.current_theme())

    def create_theme(self):
        existing = self.all_themes()
        default = tm.unique_theme_name(tr("Theme {number}").format(number=len(existing) + 1), existing)
        name = ask_theme_name(self, tr("New theme"), tr("Name of the new theme (created from the current map):"), default, existing)
        if not name:
            return
        self.project.mapThemeCollection().insert(name, tm.current_map_state(self.iface, self.project))
        self._refresh_theme_list()
        self.select_themes([name])

    def duplicate_theme(self):
        theme = self.current_theme()
        if not theme:
            return
        existing = self.all_themes()
        default = tm.unique_theme_name(tr("{theme} copy").format(theme=theme), existing)
        name = ask_theme_name(self, tr("Duplicate theme"), tr("Name of the copy:"), default, existing)
        if not name:
            return
        collection = self.project.mapThemeCollection()
        collection.insert(name, collection.mapThemeState(theme))
        self._refresh_theme_list()
        self.select_themes([name])

    def rename_current_theme(self):
        item = self.theme_list.currentItem()
        if item is not None and len(self.selected_themes()) == 1:
            self.theme_list.editItem(item, 0)

    def replace_theme(self):
        theme = self.current_theme()
        if not theme:
            return
        reply = QtWidgets.QMessageBox.question(
            self, tr("Replace theme"),
            tr("Replace «{theme}» with the layers currently visible on the map?").format(theme=theme))
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.project.mapThemeCollection().update(theme, tm.current_map_state(self.iface, self.project))
        self.record_cache = {key: value for key, value in self.record_cache.items() if key[0] != theme}

    def delete_themes(self):
        themes = self.selected_themes()
        if not themes:
            return
        if len(themes) == 1:
            question = tr("Delete the theme «{theme}»?").format(theme=themes[0])
        else:
            shown = "\n".join("• " + theme for theme in themes[:15])
            if len(themes) > 15:
                shown += "\n" + tr("… and {count} more").format(count=len(themes) - 15)
            question = tr("Delete these {count} themes?").format(count=len(themes)) + "\n\n" + shown
        reply = QtWidgets.QMessageBox.question(self, tr("Delete themes"), question)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        collection = self.project.mapThemeCollection()
        for theme in themes:
            collection.removeMapTheme(theme)
        self.record_cache = {key: value for key, value in self.record_cache.items() if key[0] not in themes}

    # ---- export / import ------------------------------------------------ #
    def _last_dir(self):
        return setting("dialog/last_dir", "") or os.path.dirname(self.project.fileName() or "")

    def export_themes(self):
        themes = sorted(self.all_themes(), key=natural_key)
        if not themes:
            return
        dialog = ExportDialog(themes, self.selected_themes(), self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        selected = dialog.selected_themes()
        default_name = (selected[0] if len(selected) == 1 else (self.project.baseName() or "themes")) + ".xml"
        default_name = re.sub(r'[\\/:*?"<>|]', "_", default_name)
        file_path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, tr("Export themes"), os.path.join(self._last_dir(), default_name), tr("Theme Manager file (*.xml)"))
        if not file_path:
            return
        if not file_path.lower().endswith(".xml"):
            file_path += ".xml"
        set_setting("dialog/last_dir", os.path.dirname(file_path))
        metadata = dialog.metadata()
        metadata["export_date"] = datetime.datetime.now().isoformat(timespec="seconds")
        metadata["plugin_version"] = plugin_version()
        try:
            theme_xml.write_themes(file_path, selected, metadata, self.project)
        except theme_xml.ThemeFileError as error:
            QtWidgets.QMessageBox.warning(self, tr("Export themes"), tr("Could not write the file:\n{error}").format(error=error))
            return
        self.iface.messageBar().pushSuccess(
            tr("Theme Manager"), tr("{count} theme(s) exported to {file}").format(count=len(selected), file=file_path))

    def import_themes(self):
        file_path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, tr("Import themes"), self._last_dir(), tr("Theme Manager file (*.xml);;All files (*)"))
        if not file_path:
            return
        set_setting("dialog/last_dir", os.path.dirname(file_path))
        try:
            metadata, themes = theme_xml.read_themes(file_path)
        except theme_xml.ThemeFileError:
            QtWidgets.QMessageBox.warning(self, tr("Import themes"), tr("The selected file is not a valid Theme Manager export."))
            return
        existing = set(self.all_themes())
        dialog = ImportDialog(metadata, [theme["name"] for theme in themes], existing, self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        chosen = set(dialog.selected_themes())
        policy = dialog.conflict_policy()
        themes = [theme for theme in themes if theme["name"] in chosen
                  and not (policy == ImportDialog.SKIP and theme["name"] in existing)]
        if not themes:
            return

        layer_infos = [info for theme in themes for info in theme["layers"] if info.get("visible", "1") == "1"]
        matches = theme_xml.match_layers(layer_infos, self.project)
        mapping = {key: best for key, (best, _candidates) in matches.items()}
        unresolved = [key for key, (best, _candidates) in matches.items() if best is None]
        if unresolved:
            infos = {theme_xml.layer_key(info): info for info in layer_infos}
            rows = []
            for key in unresolved:
                info = infos[key]
                candidates = matches[key][1]
                rows.append({
                    "key": key,
                    "label": info.get("name") or tr("(no name)"),
                    "detail": "{}\n{}".format(info.get("provider", ""), info.get("source", "")),
                    "default": candidates[0].id() if candidates else KEEP,
                })
            choices = [(tr("— ignore this layer —"), KEEP, None)] + self._layer_choices()
            mapper = MappingDialog(
                tr("Import themes — layers"),
                tr("These layers of the file were not found automatically in the project. "
                   "Choose the project layer to use for each of them, or ignore them."),
                [{"id": "layers", "title": tr("Layers not found ({count})").format(count=len(rows)), "rows": rows, "choices": choices}],
                tr("Import"), self)
            if mapper.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return
            for key, layer_id in mapper.result_values().get("layers", {}).items():
                mapping[key] = self.project.mapLayer(layer_id) if layer_id else None

        collection = self.project.mapThemeCollection()
        imported = []
        for theme in themes:
            name = theme["name"]
            if name in collection.mapThemes() and policy == ImportDialog.COPY:
                name = tm.unique_theme_name(name, collection.mapThemes())
            state = theme_xml.build_theme_state(theme, mapping, self.iface, self.project)
            if name in collection.mapThemes():
                collection.update(name, state)
            else:
                collection.insert(name, state)
            imported.append(name)
        ignored = sum(1 for layer in mapping.values() if layer is None)
        message = tr("{count} theme(s) imported.").format(count=len(imported))
        if ignored:
            message += " " + tr("{count} layer(s) ignored.").format(count=ignored)
        self.iface.messageBar().pushSuccess(tr("Theme Manager"), message)
        self._refresh_theme_list()
        self.select_themes(imported)

    def _layer_choices(self):
        """[(label, layer id, icon)] for every layer of the layer tree, in tree order."""
        choices = []
        for node, path, parent in tm.walk_tree(self.project.layerTreeRoot()):
            if path is None and node.layer() is not None:
                layer = node.layer()
                label = "{}  —  {}".format(layer.name(), parent) if parent else layer.name()
                icon = QgsIconUtils.iconForLayer(layer) if QgsIconUtils is not None else None
                choices.append((label, layer.id(), icon))
        return choices

    # ---- repair --------------------------------------------------------- #
    def repair_themes(self):
        self.guard.sync()
        orphans = self.guard.orphans()
        stale = self.guard.stale_groups()
        if not orphans and not stale:
            QtWidgets.QMessageBox.information(self, tr("Repair themes"), tr("All themes are consistent with the project."))
            self._update_actions()
            return

        project_layers = list(self.project.mapLayers().values())
        by_source, by_name = {}, {}
        for layer in project_layers:
            by_source.setdefault((layer.providerType(), tm.safe_source(layer)), []).append(layer)
            by_name.setdefault(layer.name(), []).append(layer)
        layer_rows = []
        for layer_id, info in sorted(orphans.items(), key=lambda entry: entry[1].get("name", "")):
            candidates = by_source.get((info.get("provider", ""), info.get("source", "")), []) or by_name.get(info.get("name", ""), [])
            themes = sorted(info.get("themes", {}), key=natural_key)
            layer_rows.append({
                "key": layer_id,
                "label": info.get("name") or layer_id,
                "detail": tr("Source: {source}\nUsed in {count} theme(s): {themes}").format(
                    source=info.get("source", ""), count=len(themes), themes=", ".join(themes)),
                "default": candidates[0].id() if len(candidates) == 1 else KEEP,
                "icon": theme_icon("mActionRemoveLayer.svg"),
            })

        current_paths = tm.all_group_paths(self.project.layerTreeRoot())
        by_leaf = {}
        for path in current_paths:
            by_leaf.setdefault(path.rsplit("/", 1)[-1], []).append(path)
        group_rows = []
        for path, themes in sorted(stale.items()):
            candidates = by_leaf.get(path.rsplit("/", 1)[-1], [])
            group_rows.append({
                "key": path,
                "label": path,
                "detail": tr("Used in {count} theme(s): {themes}").format(
                    count=len(themes), themes=", ".join(sorted(themes, key=natural_key))),
                "default": candidates[0] if len(candidates) == 1 else KEEP,
                "icon": theme_icon("mActionFolder.svg"),
            })

        folder = theme_icon("mActionFolder.svg")
        sections = [
            {"id": "layers", "title": tr("Layers removed from the project ({count})").format(count=len(layer_rows)),
             "rows": layer_rows,
             "choices": [(tr("— keep for later —"), KEEP, None), (tr("— forget this layer —"), FORGET, None)] + self._layer_choices()},
            {"id": "groups", "title": tr("Groups not found in the layer tree ({count})").format(count=len(group_rows)),
             "rows": group_rows,
             "choices": [(tr("— leave as is —"), KEEP, None), (tr("— remove from the themes —"), REMOVE, None)]
                        + [(path, path, folder) for path in current_paths]},
        ]
        dialog = MappingDialog(
            tr("Repair themes"),
            tr("Map themes still reference layers that were removed from the project and groups that were renamed or moved. "
               "Choose what each of them should become: the themes are updated accordingly."),
            sections, tr("Repair"), self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        result = dialog.result_values()
        restore, forget = {}, []
        for layer_id, value in result.get("layers", {}).items():
            if value == FORGET:
                forget.append(layer_id)
            elif value:
                layer = self.project.mapLayer(value)
                if layer is not None:
                    restore[layer_id] = layer
        group_mapping = {}
        for path, value in result.get("groups", {}).items():
            if value == REMOVE:
                group_mapping[path] = None
            elif value:
                group_mapping[path] = value
        if forget:
            self.guard.forget_layers(forget)
        if restore:
            self.guard.restore_layers(restore)
        if group_mapping:
            self.guard.remap_groups(group_mapping)
        self.refresh_all()

