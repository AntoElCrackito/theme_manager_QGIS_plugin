# -*- coding: utf-8 -*-
"""
ThemeGuard - keeps map themes consistent when the layer tree changes.

QGIS problems it addresses:

1. Groups are stored in themes by path ("Parent/Child"). Renaming or moving
   a group (or one of its parents) leaves stale paths in every theme, so the
   group is no longer switched on when the theme is applied.
   -> the guard detects renamed/moved groups (same node object, or same set
      of layers inside) and rewrites the paths in every theme automatically.

2. When a layer is removed from the project, QGIS removes it from every
   theme for good. Re-adding the same data later (new layer id) means
   re-creating its visibility in each theme by hand.
   -> the guard remembers which themes used the removed layer and offers to
      restore it when a layer with the same data source is added, or
      manually via the "Repair themes" dialog.

Layer renames are harmless: themes reference layers by id.

What is persisted (inside the project file, element <theme-manager-snapshot>):
only the removed layers still remembered and a short fingerprint of every
group. Everything else is rebuilt from the live project. The element is
written when the project is saved (QgsProject.writeProject), so the guard
never marks the project as modified on its own.
"""

import hashlib
import json

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.core import QgsProject

from . import theme_model as tm

SNAPSHOT_TAG = "theme-manager-snapshot"
SNAPSHOT_VERSION = 1


def layers_key(layer_ids):
    """Short fingerprint of a set of layer ids (None for an empty group)."""
    if not layer_ids:
        return None
    digest = hashlib.sha1("\n".join(sorted(layer_ids)).encode("utf-8")).hexdigest()
    return digest[:16]


class ThemeGuard(QObject):
    # the list of removed layers / stale groups may have changed
    issuesChanged = pyqtSignal()
    # list of (new_layer, removed_layer_id): re-added layers matching removed ones
    restorableLayersAdded = pyqtSignal(list)
    # {old_path: new_path} after an automatic group repair
    groupsRepaired = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = QgsProject.instance()
        # {layer_id: {"name", "source", "provider", "themes": {theme: style}}}
        # for every layer used by a theme, including removed layers (orphans).
        self.layers = {}
        self._group_nodes = []   # [(node, path)] from the last sync, for rename detection
        self._group_keys = {}    # path -> layers_key, from the last sync or from the file
        self._busy = False
        self._collection = None
        self._root = None
        self._issues_key = None

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.sync)

        self._project_signals = [
            (self.project.readProject, self._on_read_project),
            (self.project.writeProject, self._on_write_project),
            (self.project.cleared, self._on_cleared),
            (self.project.layersAdded, self._on_layers_added),
            (self.project.layersWillBeRemoved, self._on_layers_will_be_removed),
        ]
        if hasattr(self.project, "mapThemeCollectionChanged"):
            self._project_signals.append((self.project.mapThemeCollectionChanged, self._connect_collection))
        for signal, slot in self._project_signals:
            signal.connect(slot)
        self._connect_collection()
        self._connect_root()
        self.sync()

    # ------------------------------------------------------------------ #
    #  Wiring
    # ------------------------------------------------------------------ #
    def unload(self):
        self._timer.stop()
        for signal, slot in self._project_signals:
            _disconnect(signal, slot)
        self._disconnect_collection()
        if self._root is not None and not sip.isdeleted(self._root):
            for signal in (self._root.nameChanged, self._root.addedChildren, self._root.removedChildren):
                _disconnect(signal, self.schedule)

    def _connect_collection(self):
        self._disconnect_collection()
        self._collection = self.project.mapThemeCollection()
        self._collection.mapThemesChanged.connect(self.schedule)
        self._collection.mapThemeChanged.connect(self.schedule)
        self._collection.mapThemeRenamed.connect(self._on_theme_renamed)
        self.schedule()

    def _disconnect_collection(self):
        if self._collection is not None and not sip.isdeleted(self._collection):
            _disconnect(self._collection.mapThemesChanged, self.schedule)
            _disconnect(self._collection.mapThemeChanged, self.schedule)
            _disconnect(self._collection.mapThemeRenamed, self._on_theme_renamed)
        self._collection = None

    def _connect_root(self):
        self._root = self.project.layerTreeRoot()
        self._root.nameChanged.connect(self.schedule)
        self._root.addedChildren.connect(self.schedule)
        self._root.removedChildren.connect(self.schedule)

    def schedule(self, *args):
        if not self._busy:
            self._timer.start()

    # ------------------------------------------------------------------ #
    #  Project events
    # ------------------------------------------------------------------ #
    def _on_cleared(self):
        self.layers = {}
        self._group_nodes = []
        self._group_keys = {}
        self.schedule()

    def _on_read_project(self, doc):
        orphans, groups = {}, {}
        elements = doc.elementsByTagName(SNAPSHOT_TAG)
        if elements.count():
            try:
                data = json.loads(elements.at(0).toElement().text())
                if isinstance(data.get("orphans"), dict):
                    orphans = data["orphans"]
                if isinstance(data.get("groups"), dict):
                    groups = data["groups"]
            except (ValueError, TypeError, AttributeError):
                pass
        project_layers = self.project.mapLayers()
        self.layers = {layer_id: info for layer_id, info in orphans.items()
                       if layer_id not in project_layers and isinstance(info, dict)}
        self._group_nodes = []
        self._group_keys = {path: key for path, key in groups.items() if key}
        self.sync()

    def _on_write_project(self, doc):
        # Refresh without touching the themes: we are in the middle of a save.
        self.sync(heal=False)
        root = doc.documentElement()
        old = root.elementsByTagName(SNAPSHOT_TAG)
        for index in reversed(range(old.count())):
            node = old.at(index)
            node.parentNode().removeChild(node)
        data = {
            "version": SNAPSHOT_VERSION,
            "orphans": self.orphans_raw(),
            "groups": {path: key for path, key in self._group_keys.items() if key},
        }
        if not data["orphans"] and not data["groups"]:
            return
        element = doc.createElement(SNAPSHOT_TAG)
        element.setAttribute("version", str(SNAPSHOT_VERSION))
        element.appendChild(doc.createTextNode(json.dumps(data, ensure_ascii=False, sort_keys=True)))
        root.appendChild(element)

    def _on_theme_renamed(self, old_name, new_name):
        for info in self.layers.values():
            themes = info.get("themes", {})
            if old_name in themes:
                themes[new_name] = themes.pop(old_name)
        self.schedule()

    def _on_layers_will_be_removed(self, layer_ids):
        # Keep an up to date description (name may have changed since the last sync).
        for layer_id in layer_ids:
            layer = self.project.mapLayer(layer_id)
            if layer is not None and layer_id in self.layers:
                self.layers[layer_id].update(tm.layer_fingerprint(layer))
        self.schedule()

    def _on_layers_added(self, layers):
        self.schedule()
        orphans = self.orphans()
        if not orphans:
            return
        by_source = {}
        for orphan_id, info in orphans.items():
            if info.get("source"):
                by_source.setdefault((info.get("provider", ""), info["source"]), []).append(orphan_id)
        matches = []
        for layer in layers:
            candidates = by_source.get((layer.providerType(), tm.safe_source(layer)), [])
            if len(candidates) == 1:
                matches.append((layer, candidates[0]))
        if matches:
            self.restorableLayersAdded.emit(matches)

    # ------------------------------------------------------------------ #
    #  Synchronisation
    # ------------------------------------------------------------------ #
    def sync(self, heal=True):
        if self._busy:
            return
        self._busy = True
        self._timer.stop()
        repaired = {}
        try:
            root = self.project.layerTreeRoot()
            collection = self.project.mapThemeCollection()
            groups = tm.tree_groups(root)
            if heal:
                repaired = self._heal_groups(collection, root, groups)
            self._refresh_layers(collection)
            self._group_nodes = [(node, path) for node, path, _ids in groups]
            self._group_keys = {path: layers_key(ids) for _node, path, ids in groups}
        finally:
            self._busy = False
        if repaired:
            self.groupsRepaired.emit(repaired)
        self._emit_issues_if_changed()

    def _heal_groups(self, collection, root, groups):
        current_paths = {path for _node, path, _ids in groups}
        stale = set()
        for theme in collection.mapThemes():
            state = collection.mapThemeState(theme)
            stale |= (set(state.checkedGroupNodes()) | set(state.expandedGroupNodes())) - current_paths
        if not stale:
            return {}

        mapping = {}
        # 1. Same node object, renamed or moved during this session.
        for node, old_path in self._group_nodes:
            if old_path not in stale or sip.isdeleted(node) or not tm.is_attached(node, root):
                continue
            new_path = tm.group_path(node)
            if new_path != old_path and new_path in current_paths:
                mapping[old_path] = new_path

        # 2. A new group containing exactly the same layers (drag & drop clones
        #    the nodes; renames made while the plugin was not running).
        previous = self._group_keys
        by_key = {}
        for _node, path, ids in groups:
            key = layers_key(ids)
            if key and path not in previous:
                by_key.setdefault(key, []).append(path)
        used = set(mapping.values())
        for old_path in sorted(stale - set(mapping)):
            key = previous.get(old_path)
            if not key:
                continue
            candidates = [path for path in by_key.get(key, []) if path not in used]
            if len(candidates) > 1:
                leaf = old_path.rsplit("/", 1)[-1]
                candidates = [path for path in candidates if path.rsplit("/", 1)[-1] == leaf] or candidates
            if len(candidates) == 1:
                mapping[old_path] = candidates[0]
                used.add(candidates[0])

        # 3. Sub-groups of a renamed/moved parent.
        for old_path in sorted(stale - set(mapping)):
            parts = old_path.split("/")
            for cut in range(len(parts) - 1, 0, -1):
                prefix = "/".join(parts[:cut])
                if prefix in mapping:
                    candidate = mapping[prefix] + "/" + "/".join(parts[cut:])
                    if candidate in current_paths:
                        mapping[old_path] = candidate
                    break

        if not mapping:
            return {}
        edit = tm.ThemeEdit(self.project)
        for theme in collection.mapThemes():
            edit.remap_groups(theme, mapping)
        edit.commit()
        return mapping

    def _refresh_layers(self, collection):
        project_layers = self.project.mapLayers()
        themes = set(collection.mapThemes())
        layers = {}
        for theme in themes:
            for record in collection.mapThemeState(theme).layerRecords():
                layer = record.layer()
                if layer is None or not tm.record_is_visible(record):
                    continue
                info = layers.get(layer.id())
                if info is None:
                    info = tm.layer_fingerprint(layer)
                    info["themes"] = {}
                    layers[layer.id()] = info
                info["themes"][theme] = tm.record_style(record) if len(tm.layer_styles(layer)) > 1 else ""
        # Layers that disappeared from the project: QGIS removed them from the
        # themes, we keep remembering them so they can be restored later.
        for layer_id, info in self.layers.items():
            if layer_id in project_layers or layer_id in layers:
                continue
            kept = {theme: style for theme, style in info.get("themes", {}).items() if theme in themes}
            if kept:
                info = dict(info)
                info["themes"] = kept
                layers[layer_id] = info
        self.layers = layers

    def _emit_issues_if_changed(self):
        key = (tuple(sorted(self.orphans())), tuple(sorted(self.stale_groups())))
        if key != self._issues_key:
            self._issues_key = key
            self.issuesChanged.emit()

    # ------------------------------------------------------------------ #
    #  Public API used by the dialog
    # ------------------------------------------------------------------ #
    def orphans_raw(self):
        project_layers = self.project.mapLayers()
        return {layer_id: info for layer_id, info in self.layers.items() if layer_id not in project_layers}

    def orphans(self):
        """Removed layers still remembered by some theme.

        {layer_id: {"name", "source", "provider", "themes": {theme: style}}}
        """
        return self.orphans_raw()

    def stale_groups(self):
        """Group paths used by themes but absent from the layer tree: {path: [themes]}."""
        collection = self.project.mapThemeCollection()
        current = set(tm.all_group_paths(self.project.layerTreeRoot()))
        result = {}
        for theme in collection.mapThemes():
            state = collection.mapThemeState(theme)
            if not state.hasCheckedStateInfo():
                continue
            for path in state.checkedGroupNodes():
                if path not in current:
                    result.setdefault(path, []).append(theme)
        return result

    def theme_issues(self, theme):
        """(number of removed layers, number of stale groups) for one theme."""
        removed = sum(1 for info in self.orphans().values() if theme in info.get("themes", {}))
        stale = sum(1 for themes in self.stale_groups().values() if theme in themes)
        return removed, stale

    def issue_count(self):
        return len(self.orphans()) + len(self.stale_groups())

    def restore_layers(self, mapping):
        """mapping: {removed_layer_id: QgsMapLayer} - put the layers back into their themes."""
        orphans = self.orphans()
        existing = set(self.project.mapThemeCollection().mapThemes())
        edit = tm.ThemeEdit(self.project)
        for orphan_id, layer in mapping.items():
            info = orphans.get(orphan_id)
            if info is None or layer is None:
                continue
            for theme, style in info.get("themes", {}).items():
                if theme in existing and not edit.layer_visible(theme, layer.id()):
                    edit.add_record(theme, tm.new_layer_record(layer, style=style or None))
            self.layers.pop(orphan_id, None)
        edit.commit()
        self.sync()

    def forget_layers(self, layer_ids):
        for layer_id in layer_ids:
            self.layers.pop(layer_id, None)
        self._emit_issues_if_changed()

    def remap_groups(self, mapping):
        """mapping: {stale_path: new_path, or None to remove the path from the themes}"""
        edit = tm.ThemeEdit(self.project)
        for theme in self.project.mapThemeCollection().mapThemes():
            edit.remap_groups(theme, mapping)
        edit.commit()
        self.sync()


def _disconnect(signal, slot):
    try:
        signal.disconnect(slot)
    except (TypeError, RuntimeError):
        pass
