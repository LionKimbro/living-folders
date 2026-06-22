"""Filesystem boundary and folder-local world model for Living Folders."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path


MANIFEST_NAME = ".living-folder.json"
MANIFEST_ALIASES = (MANIFEST_NAME, ".directory-role.json", ".decorator.json")

PRESENTATION_MODES = [
    "directory-map",
    "project-root",
    "control-panel",
    "workbench",
    "factory",
    "library",
    "gallery",
    "inbox",
    "vault",
    "warehouse",
    "hallway",
    "ruin",
]

RUNNABLE_SUFFIXES = {
    ".bat",
    ".cmd",
    ".com",
    ".exe",
    ".ps1",
    ".py",
    ".sh",
}

TEXT_SUFFIXES = {
    ".md",
    ".rst",
    ".txt",
    ".log",
    ".csv",
    ".tsv",
}


def inspect_folder(path):
    """Normalize one directory and its constitution into the trusted world shape."""
    folder = normalize_folder_path(path)
    manifest_path, raw = read_manifest(folder)
    entries = read_entries(folder)
    inferred = infer_presentation(folder, entries)
    explicit = normalize_optional_mode(raw.get("presentation-mode"))
    buttons = normalize_buttons(raw)
    command_annotations = normalize_command_annotations(raw)
    geometry = normalize_map_geometry(raw)
    map_texts = normalize_map_texts(raw)

    return {
        "folder": str(folder),
        "manifest-path": str(manifest_path) if manifest_path else None,
        "raw-manifest": raw,
        "title": str(raw.get("title", prettify_name(folder.name))),
        "purpose": str(raw.get("purpose", infer_purpose(inferred))),
        "role": normalize_mode(raw.get("role", inferred)),
        "inferred-presentation": inferred,
        "explicit-presentation": explicit,
        "active-presentation": explicit or inferred,
        "trust-runnable-code": raw.get("trust-runnable-code") is True,
        "buttons": buttons,
        "command-annotations": command_annotations,
        "detected-buttons": detect_runnable_buttons(
            folder,
            entries,
            command_annotations,
        ),
        "map-geometry": geometry,
        "map-texts": map_texts,
        "entries": entries,
    }


def normalize_folder_path(path):
    """Admit an external path only if it resolves to an existing directory."""
    folder = Path(path).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Not a readable folder: {folder}")
    return folder


def read_manifest(folder):
    for name in MANIFEST_ALIASES:
        path = folder / name
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Cannot read {path.name}: {error}") from error
        if not isinstance(data, dict):
            raise ValueError(f"{path.name} must contain a JSON object.")
        return path, data
    return None, {}


def read_entries(folder):
    entries = []
    hidden = set(MANIFEST_ALIASES) | {".git", ".living-folders"}
    try:
        paths = sorted(folder.iterdir(), key=lambda item: item.name.lower())
    except OSError as error:
        raise ValueError(f"Cannot read folder: {error}") from error

    for path in paths:
        if path.name in hidden:
            continue
        try:
            is_folder = path.is_dir()
            size = None if is_folder else path.stat().st_size
        except OSError:
            continue
        entries.append(
            {
                "name": path.name,
                "path": str(path),
                "kind": "folder" if is_folder else "file",
                "visual-kind": classify_entry(path, is_folder),
                "size": size,
            }
        )
    return entries


def classify_entry(path, is_folder):
    if is_folder:
        return "folder"
    suffix = path.suffix.lower()
    if suffix in RUNNABLE_SUFFIXES:
        return "executable"
    if suffix == ".json":
        return "json"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
        return "image"
    return "file"


def infer_presentation(folder, entries):
    names = {entry["name"].lower() for entry in entries}
    files = [entry for entry in entries if entry["kind"] == "file"]
    suffixes = {Path(entry["name"]).suffix.lower() for entry in files}

    if (folder / ".git").exists() or {"pyproject.toml", "package.json"} & names:
        return "project-root"
    if {"inbox", "outbox"} <= names or {"input", "output"} <= names:
        return "factory"
    if "archive" in folder.name.lower() or folder.name.lower().startswith("old"):
        return "ruin"
    if suffixes and suffixes <= {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
        return "gallery"
    if "inbox" in folder.name.lower():
        return "inbox"
    return "workbench"


def normalize_optional_mode(value):
    if value in (None, "", "auto"):
        return None
    return normalize_mode(value)


def normalize_mode(value):
    mode = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    return mode or "workbench"


def normalize_buttons(raw):
    source = raw.get("buttons")
    if source is None:
        source = raw.get("actions", [])
    if not isinstance(source, list):
        raise ValueError("manifest.buttons must be an array.")

    buttons = []
    for number, item in enumerate(source, 1):
        if not isinstance(item, dict):
            raise ValueError(f"manifest.buttons item {number} must be an object.")
        kind = str(item.get("kind", "command" if "command" in item else "navigate"))
        if kind not in {"command", "navigate"}:
            raise ValueError(f"manifest.buttons item {number} has unknown kind: {kind}")

        button = {
            "id": str(item.get("id", uuid.uuid4())),
            "kind": kind,
            "label": str(item.get("label", f"Button {number}")),
            "description": str(item.get("description", "")),
        }
        if kind == "navigate":
            target = item.get("target", item.get("path", ""))
            button["target"] = str(target)
        else:
            command = item.get("command", "")
            if not isinstance(command, (str, list)):
                raise ValueError(
                    f"manifest.buttons item {number} command must be text or an array."
                )
            if isinstance(command, list) and not all(
                isinstance(part, str) for part in command
            ):
                raise ValueError(
                    f"manifest.buttons item {number} command array must contain text."
                )
            button["command"] = command
        buttons.append(button)
    return buttons


def normalize_command_annotations(raw):
    source = raw.get("commands", {})
    if not isinstance(source, dict):
        raise ValueError("manifest.commands must be an object.")
    annotations = {}
    for filename, value in source.items():
        if isinstance(value, str):
            value = {"label": value}
        if not isinstance(value, dict):
            raise ValueError(f"manifest.commands.{filename} must be an object or string.")
        annotations[str(filename)] = {
            "label": str(value.get("label", "")),
            "description": str(value.get("description", "")),
            "hidden": value.get("hidden") is True,
        }
    return annotations


def normalize_map_geometry(raw):
    section = raw.get("directory-map", {})
    if not isinstance(section, dict):
        raise ValueError("manifest.directory-map must be an object.")
    items = section.get("items", {})
    if not isinstance(items, dict):
        raise ValueError("manifest.directory-map.items must be an object.")

    geometry = {}
    for name, value in items.items():
        if not isinstance(value, dict):
            continue
        try:
            x = int(value["x"])
            y = int(value["y"])
            width = max(70, int(value["width"]))
            height = max(44, int(value["height"]))
        except (KeyError, TypeError, ValueError):
            continue
        geometry[str(name)] = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }
    return geometry


def normalize_map_texts(raw):
    section = raw.get("directory-map", {})
    if not isinstance(section, dict):
        raise ValueError("manifest.directory-map must be an object.")
    source = section.get("texts", [])
    if not isinstance(source, list):
        raise ValueError("manifest.directory-map.texts must be an array.")

    texts = []
    for number, value in enumerate(source, 1):
        if not isinstance(value, dict):
            raise ValueError(
                f"manifest.directory-map.texts item {number} must be an object."
            )
        alignment = str(value.get("alignment", "left")).lower()
        size = str(value.get("font-size", "medium")).lower()
        color = str(value.get("color", "white")).lower()
        if alignment not in {"left", "center", "right"}:
            alignment = "left"
        if size not in {"small", "medium", "large"}:
            size = "medium"
        if color not in {"white", "green", "blue", "red"}:
            color = "white"
        texts.append(
            {
                "id": str(value.get("id", uuid.uuid4())),
                "text": str(value.get("text", "")),
                "x": int(value.get("x", 40)),
                "y": int(value.get("y", 40)),
                "alignment": alignment,
                "font-size": size,
                "color": color,
            }
        )
    return texts


def detect_runnable_buttons(folder, entries, annotations):
    buttons = []
    for entry in entries:
        if entry["visual-kind"] != "executable":
            continue
        note = annotations.get(entry["name"], {})
        if note.get("hidden") is True:
            continue
        buttons.append(
            {
                "id": f"detected:{entry['name']}",
                "kind": "command",
                "source": "detected",
                "filename": entry["name"],
                "label": note.get("label") or prettify_name(Path(entry["name"]).stem),
                "description": note.get("description") or entry["name"],
                "command": command_for_path(folder / entry["name"]),
            }
        )
    return buttons


def command_for_path(path):
    suffix = path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(path)]
    if suffix == ".ps1":
        return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if suffix in {".bat", ".cmd"}:
        return ["cmd", "/c", str(path)]
    if suffix == ".sh":
        return ["sh", str(path)]
    return [str(path)]


def resolve_navigation_target(folder, target):
    path = Path(target).expanduser()
    if not path.is_absolute():
        path = folder / path
    return normalize_folder_path(path)


def write_manifest(folder, raw):
    """Atomically write a folder constitution while preserving unknown fields."""
    folder = normalize_folder_path(folder)
    target = folder / MANIFEST_NAME
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(raw, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return target


def save_presentation(folder, mode):
    _path, raw = read_manifest(normalize_folder_path(folder))
    if mode is None:
        raw.pop("presentation-mode", None)
    else:
        raw["presentation-mode"] = normalize_mode(mode)
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_code_trust(folder, trusted):
    """Persist whether this particular folder's runnable code is trusted."""
    _path, raw = read_manifest(normalize_folder_path(folder))
    raw["trust-runnable-code"] = bool(trusted)
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_buttons(folder, buttons):
    _path, raw = read_manifest(normalize_folder_path(folder))
    raw["buttons"] = buttons
    raw.pop("actions", None)
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_command_annotations(folder, annotations):
    """Persist labels and tombstones for detected executable-file buttons."""
    _path, raw = read_manifest(normalize_folder_path(folder))
    raw["commands"] = annotations
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_map_geometry(folder, geometry):
    _path, raw = read_manifest(normalize_folder_path(folder))
    section = raw.setdefault("directory-map", {})
    section["items"] = geometry
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_map_texts(folder, texts):
    _path, raw = read_manifest(normalize_folder_path(folder))
    section = raw.setdefault("directory-map", {})
    section["texts"] = texts
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def delete_immediate_file(folder, path):
    """Delete one immediate regular file after the GUI has confirmed intent."""
    folder = normalize_folder_path(folder)
    target = Path(path).expanduser().resolve()
    if target.parent != folder:
        raise ValueError("Living Folders only deletes immediate files in the open folder.")
    if not target.is_file():
        raise ValueError(f"Not a deletable file: {target.name}")
    target.unlink()


def write_manifest_template(path):
    folder = normalize_folder_path(path)
    target = folder / MANIFEST_NAME
    if target.exists():
        raise ValueError(f"{target.name} already exists.")
    entries = read_entries(folder)
    inferred = infer_presentation(folder, entries)
    raw = {}
    ensure_manifest_identity(raw, folder)
    raw["role"] = inferred
    raw["purpose"] = infer_purpose(inferred)
    raw["buttons"] = []
    raw["directory-map"] = {"items": {}, "texts": []}
    return write_manifest(folder, raw)


def ensure_manifest_identity(raw, folder):
    path = Path(folder)
    raw.setdefault("living-folder", "0.2")
    raw.setdefault("title", prettify_name(path.name))


def infer_purpose(mode):
    purposes = {
        "project-root": "A software project and its local controls.",
        "factory": "Inputs, stages, and outputs live here.",
        "gallery": "Visual material is arranged for browsing.",
        "inbox": "Incoming material waits for attention.",
        "library": "Reference material lives here for retrieval.",
        "ruin": "Old ground retained for memory or recovery.",
        "vault": "Important material is kept deliberately.",
        "workbench": "Active material is being shaped here.",
    }
    return purposes.get(mode, "A folder presenting itself as a useful place.")


def prettify_name(value):
    text = value.replace("-", " ").replace("_", " ").strip()
    return " ".join(word.capitalize() for word in text.split()) or "Untitled Folder"
