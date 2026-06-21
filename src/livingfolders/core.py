"""Read a directory at the castle gate and produce a trusted folder portrait."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_NAMES = (
    ".living-folder.json",
    ".directory-role.json",
    ".decorator.json",
)

RUNNABLE_SUFFIXES = {
    ".bat": "batch",
    ".cmd": "command",
    ".com": "program",
    ".exe": "program",
    ".ps1": "powershell",
    ".py": "python",
}

ROLE_VOCABULARY = {
    "cockpit",
    "factory",
    "gallery",
    "hallway",
    "inbox",
    "library",
    "project-root",
    "ruin",
    "staging-area",
    "vault",
    "warehouse",
    "workbench",
}


def inspect_folder(path):
    """Return the canonical portrait consumed by the GUI and JSON inspector."""
    folder = normalize_folder_path(path)
    manifest_path, raw_manifest = read_manifest(folder)
    manifest = normalize_manifest(raw_manifest, folder)
    entries = read_entries(folder, manifest)
    commands = find_commands(folder, manifest, entries)
    signals = calculate_signals(folder, entries, manifest)

    return {
        "folder": str(folder),
        "manifest-path": str(manifest_path) if manifest_path else None,
        "manifest": manifest,
        "signals": signals,
        "commands": commands,
        "entries": entries,
    }


def normalize_folder_path(path):
    """Admit an external path only after it resolves to an existing directory."""
    folder = Path(path).expanduser().resolve()
    if not folder.exists():
        raise ValueError(f"Folder does not exist: {folder}")
    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder}")
    return folder


def read_manifest(folder):
    """Read the first recognized local constitution, if one is present."""
    for name in MANIFEST_NAMES:
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


def normalize_manifest(raw, folder):
    """Turn permissive external metadata into the one interior shape."""
    role = normalize_role(raw.get("role", infer_role(folder)))
    places = raw.get("places", {})
    commands = raw.get("commands", {})
    actions = raw.get("actions", [])

    if not isinstance(places, dict):
        raise ValueError("manifest.places must be an object.")
    if not isinstance(commands, dict):
        raise ValueError("manifest.commands must be an object.")
    if not isinstance(actions, list):
        raise ValueError("manifest.actions must be an array.")

    return {
        "living-folder": str(raw.get("living-folder", "0.1")),
        "title": str(raw.get("title", prettify_name(folder.name))),
        "role": role,
        "state": str(raw.get("state", infer_state(role))),
        "presentation": str(raw.get("presentation", infer_presentation(role))),
        "purpose": str(raw.get("purpose", infer_purpose(role))),
        "mood": str(raw.get("mood", infer_mood(role))),
        "warning": str(raw.get("warning", "")),
        "places": normalize_places(places),
        "commands": normalize_command_annotations(commands),
        "actions": normalize_actions(actions),
    }


def normalize_role(value):
    role = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    return role or "workbench"


def normalize_places(raw):
    places = {}
    for name, value in raw.items():
        if isinstance(value, str):
            value = {"label": value}
        if not isinstance(value, dict):
            raise ValueError(f"manifest.places.{name} must be an object or string.")

        places[str(name)] = {
            "label": str(value.get("label", prettify_name(str(name)))),
            "role": normalize_role(value.get("role", "hallway")),
            "description": str(value.get("description", "")),
            "importance": str(value.get("importance", "normal")),
        }
    return places


def normalize_command_annotations(raw):
    commands = {}
    for name, value in raw.items():
        if isinstance(value, str):
            value = {"label": value}
        if not isinstance(value, dict):
            raise ValueError(f"manifest.commands.{name} must be an object or string.")

        commands[str(name)] = {
            "label": str(value.get("label", prettify_name(Path(str(name)).stem))),
            "description": str(value.get("description", "")),
            "importance": str(value.get("importance", "normal")),
        }
    return commands


def normalize_actions(raw):
    actions = []
    for number, value in enumerate(raw, 1):
        if not isinstance(value, dict):
            raise ValueError(f"manifest.actions item {number} must be an object.")
        if "command" not in value:
            raise ValueError(f"manifest.actions item {number} needs a command.")

        command = value["command"]
        if not isinstance(command, (str, list)):
            raise ValueError(f"manifest.actions item {number} command must be text or an array.")
        if isinstance(command, list):
            if not command:
                raise ValueError(f"manifest.actions item {number} command cannot be empty.")
            if not all(isinstance(part, str) for part in command):
                raise ValueError(
                    f"manifest.actions item {number} command array must contain only text."
                )

        actions.append(
            {
                "label": str(value.get("label", f"Action {number}")),
                "description": str(value.get("description", "")),
                "importance": str(value.get("importance", "normal")),
                "command": command,
            }
        )
    return actions


def read_entries(folder, manifest):
    """Read immediate children only; a portrait is orientation, not an indexer."""
    entries = []
    hidden_names = set(MANIFEST_NAMES) | {".git"}

    try:
        children = list(folder.iterdir())
    except OSError as error:
        raise ValueError(f"Cannot read folder: {error}") from error

    for path in children:
        if path.name in hidden_names:
            continue

        try:
            stat = path.stat()
        except OSError:
            continue

        kind = "folder" if path.is_dir() else "file"
        place = manifest["places"].get(path.name)
        entries.append(
            {
                "name": path.name,
                "path": str(path),
                "kind": kind,
                "size": stat.st_size if kind == "file" else None,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "age-days": max(
                    0,
                    int(
                        (
                            datetime.now(timezone.utc)
                            - datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                        ).total_seconds()
                        // 86400
                    ),
                ),
                "role": place["role"] if place else None,
                "label": place["label"] if place else prettify_name(path.name),
                "description": place["description"] if place else "",
                "importance": place["importance"] if place else "normal",
            }
        )

    entries.sort(
        key=lambda item: (
            item["kind"] != "folder",
            importance_rank(item["importance"]),
            item["name"].lower(),
        )
    )
    return entries


def find_commands(folder, manifest, entries):
    commands = []

    for entry in entries:
        if entry["kind"] != "file":
            continue

        suffix = Path(entry["name"]).suffix.lower()
        if suffix not in RUNNABLE_SUFFIXES:
            continue

        annotation = manifest["commands"].get(entry["name"], {})
        commands.append(
            {
                "source": "file",
                "name": entry["name"],
                "label": annotation.get("label", prettify_name(Path(entry["name"]).stem)),
                "description": annotation.get("description", RUNNABLE_SUFFIXES[suffix]),
                "importance": annotation.get("importance", "normal"),
                "command": command_for_path(folder / entry["name"]),
            }
        )

    for number, action in enumerate(manifest["actions"], 1):
        commands.append(
            {
                "source": "action",
                "name": f"action-{number}",
                **action,
            }
        )

    commands.sort(
        key=lambda item: (
            importance_rank(item["importance"]),
            item["label"].lower(),
        )
    )
    return commands


def command_for_path(path):
    suffix = path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, str(path)]
    if suffix == ".ps1":
        return ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    if suffix in {".bat", ".cmd"}:
        return ["cmd", "/c", str(path)]
    return [str(path)]


def calculate_signals(folder, entries, manifest):
    folders = [entry for entry in entries if entry["kind"] == "folder"]
    files = [entry for entry in entries if entry["kind"] == "file"]
    recent = [entry for entry in entries if entry["age-days"] <= 7]
    old = [entry for entry in entries if entry["age-days"] >= 365]
    newest = min(entries, key=lambda item: item["age-days"]) if entries else None
    oldest = max(entries, key=lambda item: item["age-days"]) if entries else None

    return {
        "folder-count": len(folders),
        "file-count": len(files),
        "recent-count": len(recent),
        "year-old-count": len(old),
        "newest": newest["name"] if newest else None,
        "oldest": oldest["name"] if oldest else None,
        "is-git-repository": (folder / ".git").exists(),
        "has-readme": any(
            entry["name"].lower().startswith("readme") for entry in files
        ),
        "declared-role": manifest["role"],
    }


def infer_role(folder):
    names = {path.name.lower() for path in safe_iterdir(folder)}
    suffixes = {path.suffix.lower() for path in safe_iterdir(folder) if path.is_file()}

    if ".git" in names or "pyproject.toml" in names or "package.json" in names:
        return "project-root"
    if {"inbox", "outbox"} <= names or {"input", "output"} <= names:
        return "factory"
    if "archive" in folder.name.lower() or "old" in folder.name.lower():
        return "ruin"
    if suffixes and suffixes <= {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}:
        return "gallery"
    if "inbox" in folder.name.lower():
        return "inbox"
    return "workbench"


def safe_iterdir(folder):
    try:
        return list(folder.iterdir())
    except OSError:
        return []


def infer_state(role):
    return "neglected" if role == "ruin" else "active"


def infer_presentation(role):
    if role in {"cockpit", "factory", "project-root"}:
        return "cockpit"
    if role == "gallery":
        return "gallery"
    return "place"


def infer_purpose(role):
    purposes = {
        "factory": "Inputs become outputs here.",
        "gallery": "A place for visual browsing.",
        "inbox": "Incoming material waits here for attention.",
        "library": "Reference material lives here for retrieval.",
        "project-root": "A living software project and its local tools.",
        "ruin": "An old place retained for memory or recovery.",
        "vault": "Important material is kept here deliberately.",
        "workbench": "Active material is being shaped here.",
    }
    return purposes.get(role, "An ordinary folder beginning to describe itself.")


def infer_mood(role):
    moods = {
        "factory": "humming",
        "gallery": "open",
        "inbox": "expectant",
        "library": "quiet",
        "project-root": "awake",
        "ruin": "dusty",
        "vault": "guarded",
        "workbench": "occupied",
    }
    return moods.get(role, "present")


def importance_rank(value):
    return {"primary": 0, "normal": 1, "secondary": 2}.get(value, 1)


def prettify_name(value):
    text = value.replace("-", " ").replace("_", " ").strip()
    return " ".join(word.capitalize() for word in text.split()) or "Untitled Folder"


def write_manifest_template(path):
    """Atomically place a small editable constitution into a folder."""
    folder = normalize_folder_path(path)
    target = folder / MANIFEST_NAMES[0]
    if target.exists():
        raise ValueError(f"{target.name} already exists.")

    role = infer_role(folder)
    data = {
        "living-folder": "0.1",
        "title": prettify_name(folder.name),
        "role": role,
        "state": infer_state(role),
        "purpose": infer_purpose(role),
        "mood": infer_mood(role),
        "commands": {},
        "places": {},
    }

    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return target
