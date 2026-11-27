# -*- coding: utf-8 -*-
"""
Developer tool (not shipped with the plugin): update the i18n/*.ts files from
the source code and compile them into *.qm, without needing Qt's lupdate /
lrelease (they are not part of the QGIS installers).

    python scripts/update_translations.py            # update .ts + compile .qm
    python scripts/update_translations.py --compile  # only compile .qm

Every user visible string goes through utils.tr("..."), in the single
translation context "ThemeManager". Existing translations are kept, new
strings are added as "unfinished", strings no longer used are dropped.
"""

import ast
import glob
import os
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I18N = os.path.join(ROOT, "i18n")
CONTEXT = "ThemeManager"
SOURCES = ["theme_manager.py", "theme_manager_dialog.py", "theme_dialogs.py",
           "theme_guard.py", "theme_model.py", "theme_xml.py", "utils.py"]


# --------------------------------------------------------------------------- #
#  Extraction
# --------------------------------------------------------------------------- #
def extract():
    """[(source text, file, line)] in order of first appearance."""
    seen, messages = set(), []
    for name in SOURCES:
        path = os.path.join(ROOT, name)
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), name)
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        calls.sort(key=lambda node: (node.lineno, node.col_offset))
        for node in calls:
            func = node.func
            func_name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
            if func_name != "tr" or not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value not in seen:
                seen.add(arg.value)
                messages.append((arg.value, name, node.lineno))
    return messages


# --------------------------------------------------------------------------- #
#  .ts files
# --------------------------------------------------------------------------- #
def read_ts(path):
    """{source: translation} for finished translations of our context."""
    translations = {}
    if not os.path.exists(path):
        return translations, None
    root = ET.parse(path).getroot()
    for context in root.findall("context"):
        if context.findtext("name") != CONTEXT:
            continue
        for message in context.findall("message"):
            source = message.findtext("source")
            translation = message.find("translation")
            if source is None or translation is None:
                continue
            if translation.get("type") in ("unfinished", "obsolete", "vanished") or not (translation.text or ""):
                continue
            translations[source] = translation.text
    return translations, root.get("language")


def write_ts(path, language, messages, translations):
    root = ET.Element("TS", {"version": "2.1", "language": language, "sourcelanguage": "en"})
    context = ET.SubElement(root, "context")
    ET.SubElement(context, "name").text = CONTEXT
    for source, filename, line in messages:
        message = ET.SubElement(context, "message")
        ET.SubElement(message, "location", {"filename": "../" + filename, "line": str(line)})
        ET.SubElement(message, "source").text = source
        translation = ET.SubElement(message, "translation")
        if source in translations:
            translation.text = translations[source]
        else:
            translation.set("type", "unfinished")
    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")
    with open(path, "wb") as handle:
        handle.write(b'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n')
        tree.write(handle, encoding="utf-8", xml_declaration=False)
        handle.write(b"\n")


# --------------------------------------------------------------------------- #
#  .qm writer (format read by QTranslator)
# --------------------------------------------------------------------------- #
QM_MAGIC = bytes([0x3C, 0xB8, 0x64, 0x18, 0xCA, 0xEF, 0x9C, 0x95, 0xCD, 0x21, 0x1C, 0xBF, 0x60, 0xA1, 0xBD, 0xDD])
TAG_END, TAG_TRANSLATION, TAG_SOURCE, TAG_CONTEXT, TAG_COMMENT = 1, 3, 6, 7, 8
SECTION_HASHES, SECTION_MESSAGES, SECTION_LANGUAGE = 0x42, 0x69, 0xA7


def elf_hash(data):
    h = 0
    for byte in data:
        h = ((h << 4) + byte) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xFFFFFFFF
    return h or 1


def write_qm(path, language, translations):
    messages = bytearray()
    hashes = []
    for source, translation in translations.items():
        source_bytes = source.encode("utf-8")
        hashes.append((elf_hash(source_bytes), len(messages)))
        translated = translation.encode("utf-16-be")
        context = CONTEXT.encode("utf-8")
        messages += struct.pack(">BI", TAG_TRANSLATION, len(translated)) + translated
        messages += struct.pack(">BI", TAG_SOURCE, len(source_bytes)) + source_bytes
        messages += struct.pack(">BI", TAG_COMMENT, 0)
        messages += struct.pack(">BI", TAG_CONTEXT, len(context)) + context
        messages += struct.pack(">B", TAG_END)
    hashes.sort()
    hash_table = b"".join(struct.pack(">II", h, offset) for h, offset in hashes)
    language_bytes = (language or "").encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(QM_MAGIC)
        if language_bytes:
            handle.write(struct.pack(">BI", SECTION_LANGUAGE, len(language_bytes)) + language_bytes)
        handle.write(struct.pack(">BI", SECTION_HASHES, len(hash_table)) + hash_table)
        handle.write(struct.pack(">BI", SECTION_MESSAGES, len(messages)) + bytes(messages))


def main():
    compile_only = "--compile" in sys.argv
    messages = None if compile_only else extract()
    for ts_path in sorted(glob.glob(os.path.join(I18N, "theme_manager_*.ts"))):
        translations, language = read_ts(ts_path)
        language = language or os.path.basename(ts_path)[len("theme_manager_"):-3]
        if messages is not None:
            current = {source for source, _file, _line in messages}
            translations = {source: text for source, text in translations.items() if source in current}
            write_ts(ts_path, language, messages, translations)
        write_qm(ts_path[:-3] + ".qm", language, translations)
        total = len(messages) if messages is not None else len(translations)
        print("{}: {}/{} translated".format(os.path.basename(ts_path), len(translations), total))


if __name__ == "__main__":
    main()
