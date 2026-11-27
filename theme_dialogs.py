# -*- coding: utf-8 -*-
"""Secondary dialogs: export, import and the layer/group mapping dialog."""

import getpass
import platform

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgsFilterLineEdit

from .utils import setting, set_setting, tr

CHECKED = Qt.CheckState.Checked
UNCHECKED = Qt.CheckState.Unchecked


class CheckableThemeList(QtWidgets.QWidget):
    """Filterable list of themes with check boxes and All / None buttons."""

    def __init__(self, themes, checked=None, labels=None, parent=None):
        super().__init__(parent)
        checked = set(themes if checked is None else checked)
        labels = labels or {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QtWidgets.QHBoxLayout()
        self.filter = QgsFilterLineEdit(self)
        self.filter.setShowSearchIcon(True)
        self.filter.setPlaceholderText(tr("Filter themes…"))
        self.filter.textChanged.connect(self._apply_filter)
        top.addWidget(self.filter, 1)
        for text, state in ((tr("All"), CHECKED), (tr("None"), UNCHECKED)):
            button = QtWidgets.QToolButton(self)
            button.setText(text)
            button.clicked.connect(lambda _checked=False, s=state: self._set_visible_items(s))
            top.addWidget(button)
        layout.addLayout(top)

        self.list = QtWidgets.QListWidget(self)
        for theme in themes:
            item = QtWidgets.QListWidgetItem(labels.get(theme, theme))
            item.setData(Qt.ItemDataRole.UserRole, theme)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(CHECKED if theme in checked else UNCHECKED)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)

    def _apply_filter(self, text):
        text = text.casefold()
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(bool(text) and text not in item.text().casefold())

    def _set_visible_items(self, state):
        for row in range(self.list.count()):
            item = self.list.item(row)
            if not item.isHidden():
                item.setCheckState(state)

    def checked_themes(self):
        return [self.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.list.count())
                if self.list.item(row).checkState() == CHECKED]


def _button_box(dialog, ok_text=None):
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel, dialog)
    if ok_text:
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    return buttons


class ExportDialog(QtWidgets.QDialog):
    """Choose the themes to export and fill in the file metadata, in one step."""

    def __init__(self, themes, preselected, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Export themes"))
        self.resize(480, 520)
        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel(tr("Themes to export:")))
        self.themes = CheckableThemeList(themes, preselected or themes, parent=self)
        layout.addWidget(self.themes, 1)

        form = QtWidgets.QFormLayout()
        self.author = QtWidgets.QLineEdit(setting("export/author", "") or getpass.getuser())
        self.os = QtWidgets.QLineEdit(platform.platform())
        self.description = QtWidgets.QPlainTextEdit()
        self.description.setMaximumHeight(80)
        form.addRow(tr("Author"), self.author)
        form.addRow(tr("Operating system"), self.os)
        form.addRow(tr("Description"), self.description)
        layout.addLayout(form)
        layout.addWidget(_button_box(self, tr("Export…")))

    def accept(self):
        if not self.themes.checked_themes():
            QtWidgets.QMessageBox.information(self, self.windowTitle(), tr("Select at least one theme."))
            return
        set_setting("export/author", self.author.text().strip())
        super().accept()

    def selected_themes(self):
        return self.themes.checked_themes()

    def metadata(self):
        return {
            "author": self.author.text().strip(),
            "os": self.os.text().strip(),
            "description": self.description.toPlainText().strip(),
        }


class ImportDialog(QtWidgets.QDialog):
    """Show the file metadata, choose the themes to import and what to do on name conflicts."""

    REPLACE, COPY, SKIP = "replace", "copy", "skip"

    def __init__(self, metadata, theme_names, existing, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Import themes"))
        self.resize(480, 520)
        layout = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QFormLayout()
        empty = tr("not specified")
        for label, key in ((tr("Author"), "author"), (tr("Date"), "export_date"),
                           (tr("Operating system"), "os"), (tr("Plugin version"), "plugin_version"),
                           (tr("Description"), "description")):
            value = QtWidgets.QLabel(metadata.get(key) or empty)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info.addRow(label, value)
        layout.addLayout(info)

        conflicts = [name for name in theme_names if name in existing]
        labels = {name: tr("{name}  (already exists)").format(name=name) for name in conflicts}
        layout.addWidget(QtWidgets.QLabel(tr("Themes to import:")))
        self.themes = CheckableThemeList(theme_names, theme_names, labels, self)
        layout.addWidget(self.themes, 1)

        self.policy = QtWidgets.QComboBox(self)
        self.policy.addItem(tr("Replace the existing theme"), self.REPLACE)
        self.policy.addItem(tr("Import as a copy (rename)"), self.COPY)
        self.policy.addItem(tr("Skip the theme"), self.SKIP)
        policy_row = QtWidgets.QHBoxLayout()
        policy_row.addWidget(QtWidgets.QLabel(tr("If a theme already exists:")))
        policy_row.addWidget(self.policy, 1)
        policy_widget = QtWidgets.QWidget(self)
        policy_widget.setLayout(policy_row)
        policy_row.setContentsMargins(0, 0, 0, 0)
        policy_widget.setVisible(bool(conflicts))
        layout.addWidget(policy_widget)
        layout.addWidget(_button_box(self, tr("Import")))

    def accept(self):
        if not self.themes.checked_themes():
            QtWidgets.QMessageBox.information(self, self.windowTitle(), tr("Select at least one theme."))
            return
        super().accept()

    def selected_themes(self):
        return self.themes.checked_themes()

    def conflict_policy(self):
        return self.policy.currentData()


class MappingDialog(QtWidgets.QDialog):
    """
    One dialog to map many items at once (instead of one popup per layer).

    sections: list of dicts
        {"id": str, "title": str,
         "choices": [(text, value, QIcon or None)],     # common to every row
         "rows": [{"key": any, "label": str, "detail": str, "default": value, "icon": QIcon}]}
    result(): {section_id: {row_key: chosen value}}
    """

    def __init__(self, title, intro, sections, ok_text=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 520)
        self._combos = {}
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(intro)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.tree = QtWidgets.QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("Item"), tr("Use instead")])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.header().setStretchLastSection(True)
        layout.addWidget(self.tree, 1)

        for section in sections:
            if not section["rows"]:
                continue
            top = QtWidgets.QTreeWidgetItem(self.tree, [section["title"]])
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            top.setFirstColumnSpanned(True)
            top.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for row in section["rows"]:
                item = QtWidgets.QTreeWidgetItem(top, [row["label"]])
                if row.get("icon") is not None:
                    item.setIcon(0, row["icon"])
                if row.get("detail"):
                    item.setToolTip(0, row["detail"])
                combo = QtWidgets.QComboBox(self.tree)
                combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                combo.setMinimumContentsLength(24)
                for text, value, icon in section["choices"]:
                    if icon is not None:
                        combo.addItem(icon, text, value)
                    else:
                        combo.addItem(text, value)
                index = combo.findData(row.get("default"))
                combo.setCurrentIndex(max(index, 0))
                self.tree.setItemWidget(item, 1, combo)
                self._combos[(section["id"], row["key"])] = combo
            top.setExpanded(True)
        self.tree.resizeColumnToContents(0)
        if self.tree.columnWidth(0) > 380:
            self.tree.setColumnWidth(0, 380)
        layout.addWidget(_button_box(self, ok_text))

    def result_values(self):
        result = {}
        for (section_id, key), combo in self._combos.items():
            result.setdefault(section_id, {})[key] = combo.currentData()
        return result


def ask_theme_name(parent, title, label, default, existing, current=None):
    """Ask for a non empty theme name not used by another theme. Returns None if cancelled."""
    existing = set(existing)
    name = default
    while True:
        name, ok = QtWidgets.QInputDialog.getText(parent, title, label, QtWidgets.QLineEdit.EchoMode.Normal, name)
        if not ok:
            return None
        name = name.strip()
        if not name:
            QtWidgets.QMessageBox.warning(parent, title, tr("Please enter a theme name."))
            continue
        if name != current and name in existing:
            QtWidgets.QMessageBox.warning(parent, title, tr("A theme with this name already exists."))
            continue
        return name

