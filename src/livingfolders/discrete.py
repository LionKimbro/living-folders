"""Compact semantic transition center for Living Folders."""

from copy import deepcopy


def initial_state():
    return {
        "folder": None,
        "model": None,
        "back-stack": [],
        "trust-code": False,
        "selected-entry": None,
        "status": "Ready.",
    }


def reduce(state, event):
    """Reduce one semantic event into new workspace state and explicit effects."""
    state = deepcopy(state)
    name = event["type"]
    effects = []

    if name == "NAVIGATE":
        effects.append(
            {
                "type": "LOAD_FOLDER",
                "path": event["path"],
                "remember": event.get("remember", True),
            }
        )

    elif name == "FOLDER_LOADED":
        previous = state["folder"]
        if event["remember"] and previous and previous != event["model"]["folder"]:
            state["back-stack"].append(previous)
        state["folder"] = event["model"]["folder"]
        state["model"] = event["model"]
        state["selected-entry"] = None
        state["trust-code"] = event["model"]["trust-runnable-code"]
        state["status"] = event.get("status", "Folder loaded.")
        effects.append({"type": "PROJECT"})

    elif name == "BACK":
        if state["back-stack"]:
            path = state["back-stack"].pop()
            effects.append({"type": "LOAD_FOLDER", "path": path, "remember": False})

    elif name == "REFRESH":
        effects.append(
            {"type": "LOAD_FOLDER", "path": state["folder"], "remember": False}
        )

    elif name == "SET_TRUST":
        state["trust-code"] = bool(event["value"])
        effects.append(
            {
                "type": "SAVE_CODE_TRUST",
                "folder": state["folder"],
                "trusted": state["trust-code"],
            }
        )

    elif name == "SET_PRESENTATION":
        effects.append(
            {
                "type": "SAVE_PRESENTATION",
                "folder": state["folder"],
                "mode": event["mode"],
            }
        )

    elif name == "SAVE_BUTTONS":
        effects.append(
            {
                "type": "WRITE_BUTTONS",
                "folder": state["folder"],
                "buttons": event["buttons"],
            }
        )

    elif name == "SAVE_COMMAND_ANNOTATIONS":
        effects.append(
            {
                "type": "WRITE_COMMAND_ANNOTATIONS",
                "folder": state["folder"],
                "annotations": event["annotations"],
            }
        )

    elif name == "DELETE_FILE":
        effects.append(
            {
                "type": "DELETE_FILE",
                "folder": state["folder"],
                "path": event["path"],
            }
        )

    elif name == "MAP_GEOMETRY_COMMITTED":
        geometry = deepcopy(state["model"]["map-geometry"])
        geometry[event["entry-name"]] = event["geometry"]
        state["model"]["map-geometry"] = geometry
        effects.append(
            {
                "type": "WRITE_MAP_GEOMETRY",
                "folder": state["folder"],
                "geometry": geometry,
            }
        )
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SELECT_ENTRY":
        state["selected-entry"] = event["entry-name"]
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SET_STATUS":
        state["status"] = event["text"]
        effects.append({"type": "PROJECT_STATUS"})

    else:
        raise ValueError(f"Unknown semantic event: {name}")

    return state, effects
