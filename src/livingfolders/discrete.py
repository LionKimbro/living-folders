"""Compact semantic transition center for Living Folders."""

from copy import deepcopy


def initial_state():
    return {
        "folder": None,
        "model": None,
        "back-stack": [],
        "trust-code": False,
        "selected-entry": None,
        "selected-text": None,
        "selected-image": None,
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
        state["selected-text"] = None
        state["selected-image"] = None
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

    elif name == "UPSERT_MAP_TEXT":
        texts = deepcopy(state["model"]["map-texts"])
        z_order = list(state["model"]["map-z-order"])
        updated = False
        for number, item in enumerate(texts):
            if item["id"] == event["text-item"]["id"]:
                texts[number] = deepcopy(event["text-item"])
                updated = True
                break
        if not updated:
            texts.append(deepcopy(event["text-item"]))
            z_order.append(f"text:{event['text-item']['id']}")
        state["model"]["map-texts"] = texts
        state["model"]["map-z-order"] = z_order
        effects.append(
            {
                "type": "WRITE_MAP_TEXTS",
                "folder": state["folder"],
                "texts": texts,
            }
        )
        effects.append(
            {
                "type": "WRITE_MAP_Z_ORDER",
                "folder": state["folder"],
                "z-order": z_order,
            }
        )
        effects.append({"type": "PROJECT_MAP"})

    elif name == "MAP_TEXT_GEOMETRY_COMMITTED":
        texts = deepcopy(state["model"]["map-texts"])
        for item in texts:
            if item["id"] == event["text-id"]:
                item.update(event["geometry"])
                break
        state["model"]["map-texts"] = texts
        effects.append(
            {
                "type": "WRITE_MAP_TEXTS",
                "folder": state["folder"],
                "texts": texts,
            }
        )
        effects.append({"type": "PROJECT_MAP"})

    elif name == "UPSERT_MAP_IMAGE":
        images = deepcopy(state["model"]["map-images"])
        z_order = list(state["model"]["map-z-order"])
        updated = False
        for number, item in enumerate(images):
            if item["id"] == event["image-item"]["id"]:
                images[number] = deepcopy(event["image-item"])
                updated = True
                break
        if not updated:
            images.append(deepcopy(event["image-item"]))
            z_order.append(f"image:{event['image-item']['id']}")
        state["model"]["map-images"] = images
        state["model"]["map-z-order"] = z_order
        effects.append(
            {
                "type": "WRITE_MAP_IMAGES",
                "folder": state["folder"],
                "images": images,
            }
        )
        effects.append(
            {
                "type": "WRITE_MAP_Z_ORDER",
                "folder": state["folder"],
                "z-order": z_order,
            }
        )
        effects.append({"type": "PROJECT_MAP"})

    elif name == "MAP_IMAGE_GEOMETRY_COMMITTED":
        images = deepcopy(state["model"]["map-images"])
        for item in images:
            if item["id"] == event["image-id"]:
                item.update(event["geometry"])
                break
        state["model"]["map-images"] = images
        effects.append(
            {
                "type": "WRITE_MAP_IMAGES",
                "folder": state["folder"],
                "images": images,
            }
        )
        effects.append({"type": "PROJECT_MAP"})

    elif name == "DELETE_MAP_IMAGE":
        images = [
            item
            for item in state["model"]["map-images"]
            if item["id"] != event["image-id"]
        ]
        state["model"]["map-images"] = images
        z_order = [
            key
            for key in state["model"]["map-z-order"]
            if key != f"image:{event['image-id']}"
        ]
        state["model"]["map-z-order"] = z_order
        state["selected-image"] = None
        effects.append(
            {
                "type": "WRITE_MAP_IMAGES",
                "folder": state["folder"],
                "images": images,
            }
        )
        effects.append(
            {
                "type": "WRITE_MAP_Z_ORDER",
                "folder": state["folder"],
                "z-order": z_order,
            }
        )
        effects.append({"type": "PROJECT_MAP"})

    elif name == "MOVE_MAP_LAYER":
        z_order = list(state["model"]["map-z-order"])
        key = event["key"]
        if key in z_order:
            index = z_order.index(key)
            target = index + event["direction"]
            if 0 <= target < len(z_order):
                z_order[index], z_order[target] = z_order[target], z_order[index]
        state["model"]["map-z-order"] = z_order
        effects.append(
            {
                "type": "WRITE_MAP_Z_ORDER",
                "folder": state["folder"],
                "z-order": z_order,
            }
        )
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SELECT_ENTRY":
        state["selected-entry"] = event["entry-name"]
        state["selected-text"] = None
        state["selected-image"] = None
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SELECT_MAP_TEXT":
        state["selected-entry"] = None
        state["selected-text"] = event["text-id"]
        state["selected-image"] = None
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SELECT_MAP_IMAGE":
        state["selected-entry"] = None
        state["selected-text"] = None
        state["selected-image"] = event["image-id"]
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SET_STATUS":
        state["status"] = event["text"]
        effects.append({"type": "PROJECT_STATUS"})

    else:
        raise ValueError(f"Unknown semantic event: {name}")

    return state, effects
