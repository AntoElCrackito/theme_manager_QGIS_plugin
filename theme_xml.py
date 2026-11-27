# -*- coding: utf-8 -*-
"""
Theme export / import file (XML).

The schema is the one used since Theme Manager 1.0, so files remain
readable by older versions of the plugin:

    <theme_manager_export>
      <metadata author="" os="" description="" export_date="" plugin_version=""/>
      <mapthemes>
        <maptheme name="Theme">
          <layer name="" source="" provider="" visible="1"/>
        </maptheme>
      </mapthemes>
    </theme_manager_export>

Version 2 only *adds* optional information that older readers ignore:
  * root attribute   format_version="2"
  * <layer>          id="..." (original layer id), style="..." (style used by the theme)
  * <maptheme>       group_info="1" when the theme controls group check boxes
  * <group path="Parent/Child" checked="1"/>   checked groups of the theme

Passwords are removed from data sources before writing.
"""

import xml.etree.ElementTree as ET

from qgis.core import QgsProject

from . import theme_model as tm

ROOT_TAG = "theme_manager_export"
FORMAT_VERSION = "2"


class ThemeFileError(Exception):
    pass


def write_themes(file_path, theme_names, metadata, project=None):
    project = project or QgsProject.instance()
    collection = project.mapThemeCollection()

    root = ET.Element(ROOT_TAG, {"format_version": FORMAT_VERSION})
    ET.SubElement(root, "metadata", {
        "author": metadata.get("author", ""),
        "os": metadata.get("os", ""),
        "description": metadata.get("description", ""),
        "export_date": metadata.get("export_date", ""),
        "plugin_version": metadata.get("plugin_version", ""),
    })
    mapthemes = ET.SubElement(root, "mapthemes")
    for theme in theme_names:
        state = collection.mapThemeState(theme)
        theme_elem = ET.SubElement(mapthemes, "maptheme", {"name": theme})
        for record in state.layerRecords():
            layer = record.layer()
            if layer is None or not tm.record_is_visible(record):
                continue
            attributes = {
                "name": layer.name(),
                "source": tm.safe_source(layer),
                "provider": layer.providerType(),
                "visible": "1",
                "id": layer.id(),
            }
            style = tm.record_style(record)
            if style:
                attributes["style"] = style
            ET.SubElement(theme_elem, "layer", attributes)
        if state.hasCheckedStateInfo():
            theme_elem.set("group_info", "1")
            for path in sorted(state.checkedGroupNodes()):
                ET.SubElement(theme_elem, "group", {"path": path, "checked": "1"})

    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")
    try:
        tree.write(file_path, encoding="utf-8", xml_declaration=True)
    except OSError as error:
        raise ThemeFileError(str(error))


def read_themes(file_path):
    """
    Returns (metadata, themes) where themes is a list of dicts:
        {"name": str, "layers": [ {name, source, provider, visible, id, style} ],
         "group_info": bool, "groups": [path, ...]}
    Raises ThemeFileError when the file is not a Theme Manager export.
    """
    try:
        tree = ET.parse(file_path)
    except (OSError, ET.ParseError) as error:
        raise ThemeFileError(str(error))
    root = tree.getroot()
    if root.tag != ROOT_TAG:
        raise ThemeFileError("not a Theme Manager export")

    metadata = {key: "" for key in ("author", "os", "description", "export_date", "plugin_version")}
    metadata_elem = root.find("metadata")
    if metadata_elem is not None:
        for key in metadata:
            metadata[key] = metadata_elem.get(key, "")

    mapthemes = root.find("mapthemes")
    if mapthemes is None:
        raise ThemeFileError("no <mapthemes> element")

    themes = []
    for theme_elem in mapthemes.findall("maptheme"):
        name = (theme_elem.get("name") or "").strip()
        if not name:
            continue
        layers = []
        for layer_elem in theme_elem.findall("layer"):
            layers.append({
                "name": layer_elem.get("name", ""),
                "source": layer_elem.get("source", ""),
                "provider": layer_elem.get("provider", ""),
                "visible": layer_elem.get("visible", "1"),
                "id": layer_elem.get("id", ""),
                "style": layer_elem.get("style", ""),
            })
        groups = [group.get("path", "") for group in theme_elem.findall("group")
                  if group.get("path") and group.get("checked", "1") == "1"]
        themes.append({
            "name": name,
            "layers": layers,
            "group_info": theme_elem.get("group_info") == "1",
            "groups": groups,
        })
    if not themes:
        raise ThemeFileError("no theme in file")
    return metadata, themes


# --------------------------------------------------------------------------- #
#  Layer matching
# --------------------------------------------------------------------------- #

def layer_key(info):
    """Identity of an imported layer, used to ask the user only once per layer."""
    return (info.get("id", ""), info.get("provider", ""), info.get("source", ""), info.get("name", ""))


def match_layers(layer_infos, project=None):
    """
    Try to match imported layers with project layers.
    Order: same layer id, then same provider + source, then same name.
    Returns {layer_key: (best QgsMapLayer or None, [candidate layers])}.
    """
    project = project or QgsProject.instance()
    project_layers = list(project.mapLayers().values())
    by_id = {layer.id(): layer for layer in project_layers}
    by_source, by_name = {}, {}
    for layer in project_layers:
        by_source.setdefault((layer.providerType(), tm.safe_source(layer)), []).append(layer)
        by_name.setdefault(layer.name(), []).append(layer)

    result = {}
    for info in layer_infos:
        key = layer_key(info)
        if key in result:
            continue
        layer = by_id.get(info.get("id", ""))
        if layer is not None:
            result[key] = (layer, [layer])
            continue
        candidates = by_source.get((info.get("provider", ""), info.get("source", "")), []) if info.get("source") else []
        if not candidates:
            candidates = by_name.get(info.get("name", ""), [])
        result[key] = (candidates[0] if len(candidates) == 1 else None, candidates)
    return result


def build_theme_state(theme_info, layer_mapping, iface, project=None):
    """Create a MapThemeRecord from an imported theme and {layer_key: QgsMapLayer or None}."""
    project = project or QgsProject.instance()
    root = project.layerTreeRoot()
    # Start from the current map so that themes from old files (without group
    # information) keep the current group check boxes, as before.
    state = tm.current_map_state(iface, project)
    records = {}
    for info in theme_info["layers"]:
        if info.get("visible", "1") != "1":
            continue
        layer = layer_mapping.get(layer_key(info))
        if layer is None or layer.id() in records:
            continue
        records[layer.id()] = tm.new_layer_record(layer, style=info.get("style") or None)
    state.setLayerRecords(list(records.values()))

    if theme_info.get("group_info"):
        current = tm.all_group_paths(root)
        current_set = set(current)
        by_leaf = {}
        for path in current:
            by_leaf.setdefault(path.rsplit("/", 1)[-1], []).append(path)
        checked = set()
        for path in theme_info.get("groups", []):
            if path in current_set:
                checked.add(path)
            else:
                # The group may live elsewhere in this project: match by name when unique.
                candidates = by_leaf.get(path.rsplit("/", 1)[-1], [])
                checked.add(candidates[0] if len(candidates) == 1 else path)
        state.setHasCheckedStateInfo(True)
        state.setCheckedGroupNodes(checked)
    return state
