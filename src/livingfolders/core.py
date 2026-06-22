"""Filesystem boundary and folder-local world model for Living Folders."""

from __future__ import annotations

import json
import hashlib
import io
import os
import re
import shutil
import sys
import uuid
from datetime import date, datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError


LIVING_FOLDER_DIR = ".living-folder"
DESCRIPTION_NAME = "description.json"
LEGACY_MANIFEST_NAMES = (
    ".living-folder.json",
    ".directory-role.json",
    ".decorator.json",
)
IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}

PRESENTATION_MODES = [
    "temporal",
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

ISO_DAY_PATTERN = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")


def inspect_folder(path):
    """Normalize one directory and its constitution into the trusted world shape."""
    folder = normalize_folder_path(path)
    manifest_path, raw = read_manifest(folder)
    entries = read_entries(folder)
    inferred = infer_presentation(folder, entries)
    explicit = normalize_optional_mode(raw.get("presentation-mode"))
    buttons = normalize_buttons(raw)
    command_annotations = normalize_command_annotations(raw)
    detected_buttons = detect_runnable_buttons(
        folder,
        entries,
        command_annotations,
    )
    button_order = normalize_button_order(raw, buttons, detected_buttons)
    geometry = normalize_map_geometry(raw)
    map_texts = normalize_map_texts(raw)
    map_images = normalize_map_images(raw)
    map_entry_states = normalize_map_entry_states(raw, entries, geometry)
    map_entries = reconcile_map_entries(folder, entries, map_entry_states)
    map_z_order = normalize_map_z_order(raw, map_entries, map_texts, map_images)
    temporal_view = normalize_temporal_view(raw)
    temporal = build_temporal_model(entries, temporal_view)

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
        "button-order": button_order,
        "ordered-buttons": order_folder_buttons(
            buttons,
            detected_buttons,
            button_order,
        ),
        "command-annotations": command_annotations,
        "detected-buttons": detected_buttons,
        "map-geometry": geometry,
        "map-entry-states": map_entry_states,
        "map-entries": map_entries,
        "map-incoming": incoming_map_entries(entries, map_entry_states),
        "map-ignored": ignored_map_entries(entries, map_entry_states),
        "map-texts": map_texts,
        "map-images": map_images,
        "map-z-order": map_z_order,
        "temporal-view": temporal_view,
        "temporal": temporal,
        "entries": entries,
    }


def normalize_folder_path(path):
    """Admit an external path only if it resolves to an existing directory."""
    folder = Path(path).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Not a readable folder: {folder}")
    return folder


def read_manifest(folder):
    current = folder / LIVING_FOLDER_DIR / DESCRIPTION_NAME
    if current.is_file():
        return current, read_json_object(current)

    for name in LEGACY_MANIFEST_NAMES:
        path = folder / name
        if not path.is_file():
            continue
        return path, read_json_object(path)
    return None, {}


def read_json_object(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def read_entries(folder):
    entries = []
    hidden = set(LEGACY_MANIFEST_NAMES) | {
        ".git",
        ".living-folder",
        ".living-folders",
    }
    try:
        paths = sorted(folder.iterdir(), key=lambda item: item.name.lower())
    except OSError as error:
        raise ValueError(f"Cannot read folder: {error}") from error

    for path in paths:
        if path.name in hidden:
            continue
        try:
            is_folder = path.is_dir()
            stat = path.stat()
            size = None if is_folder else stat.st_size
        except OSError:
            continue
        entries.append(
            {
                "name": path.name,
                "path": str(path),
                "kind": "folder" if is_folder else "file",
                "visual-kind": classify_entry(path, is_folder),
                "size": size,
                "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
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
    if temporal_inference_score(entries)["inferred"]:
        return "temporal"
    if "archive" in folder.name.lower() or folder.name.lower().startswith("old"):
        return "ruin"
    if suffixes and suffixes <= {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
        return "gallery"
    if "inbox" in folder.name.lower():
        return "inbox"
    return "workbench"


def temporal_inference_score(entries):
    """Measure whether immediate children form one coherent date-organized place."""
    dated = sum(bool(extract_iso_days(entry["name"])) for entry in entries)
    eligible = len(entries)
    ratio = dated / eligible if eligible else 0.0
    return {
        "dated-entry-count": dated,
        "eligible-entry-count": eligible,
        "ratio": ratio,
        "inferred": dated >= 3 and ratio >= 0.5,
    }


def extract_iso_days(name):
    """Return valid, unique ISO calendar days embedded in one entry name."""
    found = []
    for candidate in ISO_DAY_PATTERN.findall(str(name)):
        try:
            parsed = date.fromisoformat(candidate)
        except ValueError:
            continue
        normalized = parsed.isoformat()
        if normalized not in found:
            found.append(normalized)
    return found


def normalize_temporal_view(raw):
    source = raw.get("temporal-view", {})
    if not isinstance(source, dict):
        raise ValueError("manifest.temporal-view must be an object.")

    layout = str(source.get("layout", "daystream")).strip().lower()
    if layout not in {"daystream"}:
        layout = "daystream"
    resolution = str(source.get("resolution", "day")).strip().lower()
    if resolution not in {"day"}:
        resolution = "day"
    week_start = str(source.get("week-start", "monday")).strip().lower()
    if week_start not in {"monday"}:
        week_start = "monday"
    initial_position = str(
        source.get("initial-position", "most-recent")
    ).strip().lower()
    if initial_position not in {"most-recent", "today", "earliest"}:
        initial_position = "most-recent"

    hidden = source.get("hidden-file-patterns", ["*~"])
    if not isinstance(hidden, list) or not all(
        isinstance(item, str) for item in hidden
    ):
        raise ValueError(
            "manifest.temporal-view.hidden-file-patterns must be an array of strings."
        )

    return {
        "layout": layout,
        "resolution": resolution,
        "week-start": week_start,
        "initial-position": initial_position,
        "future-context-weeks": max(
            0,
            min(12, integer_or_default(source.get("future-context-weeks"), 1)),
        ),
        "hidden-file-patterns": hidden,
        "show-modification-associations": (
            source.get("show-modification-associations") is True
        ),
    }


def build_temporal_model(entries, temporal_view):
    """Project ordinary filesystem entries onto day nodes without moving them."""
    nodes = {}
    exceptions = []
    hidden = []

    for entry in entries:
        if matches_any_pattern(entry["name"], temporal_view["hidden-file-patterns"]):
            hidden.append(entry)
            continue

        day_keys = extract_iso_days(entry["name"])
        if not day_keys:
            exceptions.append(
                {
                    "entry": entry,
                    "reason": "undated",
                }
            )
            continue

        exact_name = entry["name"] in day_keys
        exact_stem = Path(entry["name"]).stem in day_keys
        for day_key in day_keys:
            node = nodes.setdefault(
                day_key,
                {
                    "date": day_key,
                    "canonical": [],
                    "associated": [],
                    "latest-modified": None,
                },
            )
            association = {
                "entry": entry,
                "confidence": (
                    "canonical"
                    if exact_name
                    else "exact-stem"
                    if exact_stem
                    else "filename"
                ),
            }
            bucket = "canonical" if exact_name else "associated"
            node[bucket].append(association)
            modified = entry.get("modified")
            if modified and (
                node["latest-modified"] is None
                or modified > node["latest-modified"]
            ):
                node["latest-modified"] = modified

    ordered = [nodes[key] for key in sorted(nodes)]
    return {
        "resolution": "day",
        "nodes": ordered,
        "node-by-date": {node["date"]: node for node in ordered},
        "exceptions": exceptions,
        "hidden": hidden,
        "earliest-date": ordered[0]["date"] if ordered else None,
        "most-recent-date": ordered[-1]["date"] if ordered else None,
        "inference": temporal_inference_score(entries),
    }


def matches_any_pattern(name, patterns):
    from fnmatch import fnmatch

    return any(fnmatch(name, pattern) for pattern in patterns)


def integer_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


def folder_button_key(button):
    if button.get("source") == "detected":
        return f"detected:{button['filename']}"
    return f"button:{button['id']}"


def normalize_button_order(raw, buttons, detected_buttons):
    source = raw.get("button-order", [])
    if not isinstance(source, list):
        raise ValueError("manifest.button-order must be an array.")
    available = [
        folder_button_key(button)
        for button in buttons + detected_buttons
    ]
    available_set = set(available)
    ordered = []
    for value in source:
        key = str(value)
        if key in available_set and key not in ordered:
            ordered.append(key)
    for key in available:
        if key not in ordered:
            ordered.append(key)
    return ordered


def order_folder_buttons(buttons, detected_buttons, button_order):
    by_key = {
        folder_button_key(button): button
        for button in buttons + detected_buttons
    }
    return [
        by_key[key]
        for key in button_order
        if key in by_key
    ]


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


def normalize_map_entry_states(raw, entries, geometry):
    """Normalize durable placement intent and migrate older map constitutions."""
    section = raw.get("directory-map", {})
    if not isinstance(section, dict):
        raise ValueError("manifest.directory-map must be an object.")
    source = section.get("entry-states")
    if source is not None and not isinstance(source, dict):
        raise ValueError("manifest.directory-map.entry-states must be an object.")

    current = {entry["name"]: entry for entry in entries}
    states = {}
    if source is not None:
        for name, value in source.items():
            if not isinstance(value, dict):
                continue
            state = str(value.get("state", "placed")).lower()
            if state not in {"placed", "ignored"}:
                continue
            live = current.get(str(name))
            states[str(name)] = {
                "state": state,
                "kind": str(value.get("kind", live["kind"] if live else "file")),
                "visual-kind": str(
                    value.get(
                        "visual-kind",
                        live["visual-kind"] if live else "file",
                    )
                ),
            }
        return states

    # Older maps implicitly treated persisted entry layers and geometry as placed.
    legacy_names = set(geometry)
    z_order = section.get("z-order", [])
    if isinstance(z_order, list):
        legacy_names.update(
            str(key).split(":", 1)[1]
            for key in z_order
            if str(key).startswith("entry:")
        )
    for name in legacy_names:
        live = current.get(name)
        states[name] = {
            "state": "placed",
            "kind": live["kind"] if live else "file",
            "visual-kind": live["visual-kind"] if live else "file",
        }
    return states


def reconcile_map_entries(folder, entries, states):
    """Return placed live entries and retained ghosts in one drawable collection."""
    current = {entry["name"]: entry for entry in entries}
    result = []
    for name, state in states.items():
        if state["state"] != "placed":
            continue
        if name in current:
            result.append({**current[name], "missing": False})
            continue
        result.append(
            {
                "name": name,
                "path": str(Path(folder) / name),
                "kind": state["kind"],
                "visual-kind": state["visual-kind"],
                "size": None,
                "modified": None,
                "missing": True,
            }
        )
    return result


def incoming_map_entries(entries, states):
    return [
        entry
        for entry in entries
        if entry["name"] not in states
    ]


def ignored_map_entries(entries, states):
    return [
        entry
        for entry in entries
        if states.get(entry["name"], {}).get("state") == "ignored"
    ]


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
        line_width = str(value.get("region-line-width", "thick")).lower()
        if line_width not in {"thin", "thick"}:
            line_width = "thick"
        texts.append(
            {
                "id": str(value.get("id", uuid.uuid4())),
                "text": str(value.get("text", "")),
                "x": int(value.get("x", 40)),
                "y": int(value.get("y", 40)),
                "alignment": alignment,
                "font-size": size,
                "color": color,
                "labelled-region": value.get("labelled-region") is True,
                "region-line-width": line_width,
                "width": max(120, int(value.get("width", 320))),
                "height": max(70, int(value.get("height", 180))),
            }
        )
    return texts


def normalize_map_images(raw):
    section = raw.get("directory-map", {})
    if not isinstance(section, dict):
        raise ValueError("manifest.directory-map must be an object.")
    source = section.get("images", [])
    if not isinstance(source, list):
        raise ValueError("manifest.directory-map.images must be an array.")

    images = []
    for number, value in enumerate(source, 1):
        if not isinstance(value, dict):
            raise ValueError(
                f"manifest.directory-map.images item {number} must be an object."
            )
        try:
            images.append(
                {
                    "id": str(value.get("id", uuid.uuid4())),
                    "asset": str(value["asset"]),
                    "source-name": str(value.get("source-name", "")),
                    "x": int(value.get("x", 40)),
                    "y": int(value.get("y", 40)),
                    "width": max(24, int(value.get("width", 240))),
                    "height": max(24, int(value.get("height", 180))),
                }
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"manifest.directory-map.images item {number} is malformed."
            ) from error
    return images


def normalize_map_z_order(raw, entries, texts, images):
    section = raw.get("directory-map", {})
    if not isinstance(section, dict):
        raise ValueError("manifest.directory-map must be an object.")
    source = section.get("z-order", [])
    if not isinstance(source, list):
        raise ValueError("manifest.directory-map.z-order must be an array.")

    available = (
        [f"entry:{item['name']}" for item in entries]
        + [f"text:{item['id']}" for item in texts]
        + [f"image:{item['id']}" for item in images]
    )
    available_set = set(available)
    ordered = []
    for value in source:
        key = str(value)
        if key in available_set and key not in ordered:
            ordered.append(key)
    for key in available:
        if key not in ordered:
            ordered.append(key)
    return ordered


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
    target = folder / LIVING_FOLDER_DIR / DESCRIPTION_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
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


def save_button_order(folder, button_order):
    _path, raw = read_manifest(normalize_folder_path(folder))
    raw["button-order"] = [str(key) for key in button_order]
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


def save_map_entry_states(folder, states):
    _path, raw = read_manifest(normalize_folder_path(folder))
    section = raw.setdefault("directory-map", {})
    section["entry-states"] = states
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_map_texts(folder, texts):
    _path, raw = read_manifest(normalize_folder_path(folder))
    section = raw.setdefault("directory-map", {})
    section["texts"] = texts
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_map_images(folder, images):
    _path, raw = read_manifest(normalize_folder_path(folder))
    section = raw.setdefault("directory-map", {})
    section["images"] = images
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def save_map_z_order(folder, z_order):
    _path, raw = read_manifest(normalize_folder_path(folder))
    section = raw.setdefault("directory-map", {})
    section["z-order"] = z_order
    ensure_manifest_identity(raw, folder)
    return write_manifest(folder, raw)


def import_image_file(folder, source, x, y):
    """Copy one image into content-addressed storage and return its map record."""
    folder = normalize_folder_path(folder)
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Image file not found: {source}")

    try:
        with Image.open(source) as image:
            image.verify()
        with Image.open(source) as image:
            source_width, source_height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"Not a supported image: {source.name}") from error

    images_dir = folder / LIVING_FOLDER_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    suffix = source.suffix.lower()
    encoded = None
    if suffix in IMAGE_SUFFIXES:
        digest = sha256_file(source)
    else:
        with Image.open(source) as image:
            encoded = encode_png(image)
        digest = hashlib.sha256(encoded).hexdigest()
        suffix = ".png"

    target = images_dir / f"{digest}{suffix}"
    if not target.exists():
        if encoded is None:
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        else:
            atomic_write_bytes(target, encoded)

    width, height = fit_image_size(source_width, source_height, 320, 240)
    return {
        "id": str(uuid.uuid4()),
        "asset": target.name,
        "source-name": source.name,
        "x": int(x),
        "y": int(y),
        "width": width,
        "height": height,
    }


def import_clipboard_image(folder, image, x, y):
    """Store an in-memory Pillow image by content hash and return its map record."""
    folder = normalize_folder_path(folder)
    images_dir = folder / LIVING_FOLDER_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    rgba = image.convert("RGBA")
    encoded = encode_png(rgba)
    digest = hashlib.sha256(encoded).hexdigest()
    target = images_dir / f"{digest}.png"
    if not target.exists():
        atomic_write_bytes(target, encoded)

    width, height = fit_image_size(rgba.width, rgba.height, 320, 240)
    return {
        "id": str(uuid.uuid4()),
        "asset": target.name,
        "source-name": "clipboard.png",
        "x": int(x),
        "y": int(y),
        "width": width,
        "height": height,
    }


def get_cached_image_path(folder, image_item):
    """Return a cached rendered PNG for one map image size, creating it atomically."""
    folder = normalize_folder_path(folder)
    images_dir = folder / LIVING_FOLDER_DIR / "images"
    source = images_dir / image_item["asset"]
    if not source.is_file():
        raise ValueError(f"Missing Living Folder image asset: {image_item['asset']}")

    stem = Path(image_item["asset"]).stem
    width = image_item["width"]
    height = image_item["height"]
    cache_dir = images_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{stem}-{width}x{height}.png"
    if target.exists():
        return target

    try:
        with Image.open(source) as image:
            rendered = image.convert("RGBA")
            rendered.thumbnail((width, height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            left = (width - rendered.width) // 2
            top = (height - rendered.height) // 2
            canvas.alpha_composite(rendered, (left, top))
            temporary = target.with_suffix(".png.tmp")
            canvas.save(temporary, format="PNG")
            os.replace(temporary, target)
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"Cannot render image asset: {source.name}") from error
    return target


def resolve_image_asset_path(folder, image_item):
    folder = normalize_folder_path(folder)
    return folder / LIVING_FOLDER_DIR / "images" / image_item["asset"]


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def encode_png(image):
    stream = io.BytesIO()
    image.convert("RGBA").save(stream, format="PNG")
    return stream.getvalue()


def atomic_write_bytes(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def fit_image_size(width, height, max_width, max_height):
    scale = min(max_width / width, max_height / height, 1.0)
    return max(24, int(width * scale)), max(24, int(height * scale))


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
    target = folder / LIVING_FOLDER_DIR / DESCRIPTION_NAME
    if target.exists():
        raise ValueError(f"{target} already exists.")
    legacy_path, _raw = read_manifest(folder)
    if legacy_path:
        raise ValueError(f"A Living Folder description already exists: {legacy_path}")
    entries = read_entries(folder)
    inferred = infer_presentation(folder, entries)
    raw = {}
    ensure_manifest_identity(raw, folder)
    raw["role"] = inferred
    raw["purpose"] = infer_purpose(inferred)
    raw["buttons"] = []
    raw["directory-map"] = {
        "entry-states": {},
        "items": {},
        "texts": [],
        "images": [],
        "z-order": [],
    }
    return write_manifest(folder, raw)


def ensure_manifest_identity(raw, folder):
    path = Path(folder)
    raw["living-folder"] = "0.3"
    raw.setdefault("title", prettify_name(path.name))


def infer_purpose(mode):
    purposes = {
        "temporal": "Filesystem entries gather into a navigable shape of time.",
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
