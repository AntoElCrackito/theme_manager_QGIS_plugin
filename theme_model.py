# -*- coding: utf-8 -*-
"""
Pure (UI free) helpers around QgsMapThemeCollection.

How QGIS stores a map theme (QgsMapThemeCollection.MapThemeRecord):
  * one MapThemeLayerRecord per *checked* layer, referenced by layer id
    (renaming a layer is therefore harmless, removing it drops the record);
  * the set of checked groups and expanded groups, referenced by their
    *path* ("Parent/Child"), so renaming or moving a group silently breaks
    every theme that uses it;
  * a flag telling whether the group state is stored at all
    (themes created by very old QGIS versions don't have it).
"""

from qgis.core import QgsDataSourceUri, QgsLayerTree, QgsMapThemeCollection, QgsProject


# --------------------------------------------------------------------------- #
#  Layer tree
# --------------------------------------------------------------------------- #

def group_path(group):
    """Path of a group as used by map themes: "Parent/Child"."""
    parts = []
    node = group
    while node is not None and node.parent() is not None:
        parts.append(node.name())
        node = node.parent()
    return "/".join(reversed(parts))


def walk_tree(node, path=""):
    """Yield (node, group_path_or_None, parent_group_path) for every descendant, depth first."""
    for child in node.children():
        if QgsLayerTree.isGroup(child):
            child_path = "{}/{}".format(path, child.name()) if path else child.name()
            yield child, child_path, path
            yield from walk_tree(child, child_path)
        elif QgsLayerTree.isLayer(child):
            yield child, None, path


def tree_groups(root):
    """List of (group_node, path, frozenset of descendant layer ids)."""
    result = []
    for node, path, _parent in walk_tree(root):
        if path is not None:
            layer_ids = frozenset(layer.layerId() for layer in node.findLayers())
            result.append((node, path, layer_ids))
    return result


def all_group_paths(root):
    return [path for _node, path, _parent in walk_tree(root) if path is not None]


def is_attached(node, root):
    while node is not None:
        if node is root:
            return True
        node = node.parent()
    return False


# --------------------------------------------------------------------------- #
#  Layers
# --------------------------------------------------------------------------- #

def safe_source(layer):
    """Layer source without any password, safe to write into a file."""
    try:
        return QgsDataSourceUri.removePassword(layer.source())
    except Exception:  # pragma: no cover - very old/odd providers
        return layer.source()


def layer_fingerprint(layer):
    return {
        "name": layer.name(),
        "source": safe_source(layer),
        "provider": layer.providerType(),
    }


def layer_styles(layer):
    try:
        return list(layer.styleManager().styles())
    except Exception:
        return []


def new_layer_record(layer, visible=True, style=None):
    record = QgsMapThemeCollection.MapThemeLayerRecord(layer)
    record.isVisible = visible
    styles = layer_styles(layer)
    if style and style in styles:
        record.usingCurrentStyle = True
        record.currentStyle = style
    elif styles:
        record.usingCurrentStyle = True
        record.currentStyle = layer.styleManager().currentStyle()
    return record


def record_is_visible(record):
    return bool(getattr(record, "isVisible", True))


def record_style(record):
    return record.currentStyle if record.usingCurrentStyle else ""


# --------------------------------------------------------------------------- #
#  Theme states
# --------------------------------------------------------------------------- #

class ThemeView:
    """Read only, cached view of one theme, cheap to query from the UI."""

    def __init__(self, state):
        self.state = state
        self.records = {}
        for record in state.layerRecords():
            layer = record.layer()
            if layer is not None:
                self.records[layer.id()] = record
        self.has_group_info = state.hasCheckedStateInfo()
        self.checked_groups = set(state.checkedGroupNodes())

    def layer_visible(self, layer_id):
        record = self.records.get(layer_id)
        return record is not None and record_is_visible(record)

    def group_checked(self, path):
        # Without group info QGIS does not touch groups when applying the theme:
        # show them as checked, which is what the user effectively gets.
        return (not self.has_group_info) or path in self.checked_groups

    def style(self, layer_id):
        record = self.records.get(layer_id)
        return record_style(record) if record is not None else ""

    def visible_count(self):
        return sum(1 for record in self.records.values() if record_is_visible(record))


class ThemeEdit:
    """
    Accumulates modifications of several themes and commits each modified
    theme once (one QgsMapThemeCollection.update() per theme), so bulk
    operations stay fast and emit few signals.

    `record_cache` keeps the records removed during the session, so
    unchecking then re-checking a layer restores its theme style and legend
    configuration instead of resetting them.
    """

    def __init__(self, project=None, record_cache=None):
        self.project = project or QgsProject.instance()
        self.collection = self.project.mapThemeCollection()
        self.record_cache = record_cache if record_cache is not None else {}
        self._states = {}
        self._records = {}
        self._dirty = set()

    def _load(self, theme):
        if theme not in self._states:
            state = self.collection.mapThemeState(theme)
            records = {}
            for record in state.layerRecords():
                layer = record.layer()
                if layer is not None:
                    records[layer.id()] = record
            self._states[theme] = state
            self._records[theme] = records
        return self._states[theme], self._records[theme]

    # -- layers ------------------------------------------------------------- #
    def layer_visible(self, theme, layer_id):
        _state, records = self._load(theme)
        record = records.get(layer_id)
        return record is not None and record_is_visible(record)

    def set_layer_visible(self, theme, layer, visible):
        _state, records = self._load(theme)
        layer_id = layer.id()
        record = records.get(layer_id)
        if visible:
            if record is not None and record_is_visible(record):
                return
            if record is None:
                record = self.record_cache.pop((theme, layer_id), None) or new_layer_record(layer)
            record.isVisible = True
            records[layer_id] = record
        else:
            if record is None:
                return
            # Same behaviour as QGIS itself: unchecked layers are not stored.
            self.record_cache[(theme, layer_id)] = records.pop(layer_id)
        self._dirty.add(theme)

    def set_layer_style(self, theme, layer, style):
        _state, records = self._load(theme)
        record = records.get(layer.id())
        if record is None:
            record = new_layer_record(layer, style=style)
            records[layer.id()] = record
        record.usingCurrentStyle = True
        record.currentStyle = style
        self._dirty.add(theme)

    def add_record(self, theme, record):
        _state, records = self._load(theme)
        records[record.layer().id()] = record
        self._dirty.add(theme)

    # -- groups ------------------------------------------------------------- #
    def group_checked(self, theme, path):
        state, _records = self._load(theme)
        return (not state.hasCheckedStateInfo()) or path in state.checkedGroupNodes()

    def set_group_checked(self, theme, path, checked, all_paths):
        state, _records = self._load(theme)
        if state.hasCheckedStateInfo():
            nodes = set(state.checkedGroupNodes())
        else:
            # The theme did not control groups so far (all groups are shown as
            # checked). Start from "everything checked" instead of "nothing
            # checked", otherwise every other group would get unchecked the
            # next time the theme is applied.
            nodes = set(all_paths)
            state.setHasCheckedStateInfo(True)
        if checked:
            nodes.add(path)
        else:
            nodes.discard(path)
        state.setCheckedGroupNodes(nodes)
        self._dirty.add(theme)

    def remap_groups(self, theme, mapping):
        """Rename group paths in a theme. mapping: old path -> new path (or None to drop)."""
        state, _records = self._load(theme)
        changed = False
        for getter, setter in ((state.checkedGroupNodes, state.setCheckedGroupNodes),
                               (state.expandedGroupNodes, state.setExpandedGroupNodes)):
            old_nodes = set(getter())
            new_nodes = set()
            for path in old_nodes:
                if path in mapping:
                    if mapping[path]:
                        new_nodes.add(mapping[path])
                else:
                    new_nodes.add(path)
            if new_nodes != old_nodes:
                setter(new_nodes)
                changed = True
        if changed:
            self._dirty.add(theme)
        return changed

    # -- commit ------------------------------------------------------------- #
    def commit(self):
        """Write every modified theme back. Returns the list of modified themes."""
        modified = []
        for theme in sorted(self._dirty):
            state = self._states[theme]
            state.setLayerRecords(list(self._records[theme].values()))
            self.collection.update(theme, state)
            modified.append(theme)
        self._dirty.clear()
        self._states.clear()
        self._records.clear()
        return modified


# --------------------------------------------------------------------------- #
#  Misc
# --------------------------------------------------------------------------- #

def layer_tree_model(iface):
    view = iface.layerTreeView()
    return view.layerTreeModel() if view is not None else None


def apply_theme(iface, theme, project=None):
    project = project or QgsProject.instance()
    project.mapThemeCollection().applyTheme(theme, project.layerTreeRoot(), layer_tree_model(iface))


def current_map_state(iface, project=None):
    project = project or QgsProject.instance()
    return QgsMapThemeCollection.createThemeFromCurrentState(project.layerTreeRoot(), layer_tree_model(iface))


def active_themes(iface, project=None):
    """Themes identical to the current state of the layer tree (what QGIS ticks in its theme menu)."""
    project = project or QgsProject.instance()
    collection = project.mapThemeCollection()
    try:
        current = current_map_state(iface, project)
        return {theme for theme in collection.mapThemes() if collection.mapThemeState(theme) == current}
    except Exception:
        return set()


def unique_theme_name(base, existing):
    existing = set(existing)
    if base not in existing:
        return base
    index = 2
    while "{} ({})".format(base, index) in existing:
        index += 1
    return "{} ({})".format(base, index)
