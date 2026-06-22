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
        "group-selection": [],
        "map-placement-entry": None,
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
        state["group-selection"] = []
        state["map-placement-entry"] = None
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

    elif name == "BEGIN_MAP_PLACEMENT":
        state["map-placement-entry"] = event["entry-name"]
        state["status"] = (
            f"Placing {event['entry-name']}: click the map or press Escape to cancel."
        )
        effects.extend(
            [
                {"type": "PROJECT_INCOMING"},
                {"type": "PROJECT_STATUS"},
            ]
        )

    elif name == "CANCEL_MAP_PLACEMENT":
        state["map-placement-entry"] = None
        state["status"] = "Placement cancelled."
        effects.extend(
            [
                {"type": "PROJECT_INCOMING"},
                {"type": "PROJECT_STATUS"},
            ]
        )

    elif name == "PLACE_MAP_ENTRY":
        name = event["entry-name"]
        entry = next(
            item
            for item in state["model"]["entries"]
            if item["name"] == name
        )
        states = deepcopy(state["model"]["map-entry-states"])
        states[name] = {
            "state": "placed",
            "kind": entry["kind"],
            "visual-kind": entry["visual-kind"],
        }
        geometry = deepcopy(state["model"]["map-geometry"])
        geometry[name] = deepcopy(event["geometry"])
        map_entries = [
            item
            for item in state["model"]["map-entries"]
            if item["name"] != name
        ]
        map_entries.append({**deepcopy(entry), "missing": False})
        incoming = [
            item
            for item in state["model"]["map-incoming"]
            if item["name"] != name
        ]
        z_order = [
            key
            for key in state["model"]["map-z-order"]
            if key != f"entry:{name}"
        ]
        z_order.append(f"entry:{name}")
        state["model"]["map-entry-states"] = states
        state["model"]["map-geometry"] = geometry
        state["model"]["map-entries"] = map_entries
        state["model"]["map-incoming"] = incoming
        state["model"]["map-z-order"] = z_order
        state["map-placement-entry"] = None
        state["selected-entry"] = name
        state["status"] = f"Placed {name} on the Directory Map."
        effects.extend(
            [
                {
                    "type": "WRITE_MAP_ENTRY_STATES",
                    "folder": state["folder"],
                    "states": states,
                },
                {
                    "type": "WRITE_MAP_GEOMETRY",
                    "folder": state["folder"],
                    "geometry": geometry,
                },
                {
                    "type": "WRITE_MAP_Z_ORDER",
                    "folder": state["folder"],
                    "z-order": z_order,
                },
                {"type": "PROJECT_DIRECTORY_MAP"},
                {"type": "PROJECT_STATUS"},
            ]
        )

    elif name == "IGNORE_MAP_ENTRY":
        name = event["entry-name"]
        entry = next(
            item
            for item in state["model"]["entries"]
            if item["name"] == name
        )
        states = deepcopy(state["model"]["map-entry-states"])
        states[name] = {
            "state": "ignored",
            "kind": entry["kind"],
            "visual-kind": entry["visual-kind"],
        }
        state["model"]["map-entry-states"] = states
        state["model"]["map-incoming"] = [
            item
            for item in state["model"]["map-incoming"]
            if item["name"] != name
        ]
        state["model"]["map-ignored"].append(deepcopy(entry))
        if state["map-placement-entry"] == name:
            state["map-placement-entry"] = None
        state["status"] = f"Ignored {name} on the Directory Map."
        effects.extend(
            [
                {
                    "type": "WRITE_MAP_ENTRY_STATES",
                    "folder": state["folder"],
                    "states": states,
                },
                {"type": "PROJECT_INCOMING"},
                {"type": "PROJECT_STATUS"},
            ]
        )

    elif name == "UNIGNORE_MAP_ENTRY":
        name = event["entry-name"]
        states = deepcopy(state["model"]["map-entry-states"])
        states.pop(name, None)
        entry = next(
            item
            for item in state["model"]["map-ignored"]
            if item["name"] == name
        )
        state["model"]["map-entry-states"] = states
        state["model"]["map-ignored"] = [
            item
            for item in state["model"]["map-ignored"]
            if item["name"] != name
        ]
        state["model"]["map-incoming"].append(deepcopy(entry))
        state["status"] = f"Returned {name} to Incoming."
        effects.extend(
            [
                {
                    "type": "WRITE_MAP_ENTRY_STATES",
                    "folder": state["folder"],
                    "states": states,
                },
                {"type": "PROJECT_INCOMING"},
                {"type": "PROJECT_STATUS"},
            ]
        )

    elif name == "REMOVE_MISSING_MAP_ENTRY":
        name = event["entry-name"]
        states = deepcopy(state["model"]["map-entry-states"])
        states.pop(name, None)
        geometry = deepcopy(state["model"]["map-geometry"])
        geometry.pop(name, None)
        z_order = [
            key
            for key in state["model"]["map-z-order"]
            if key != f"entry:{name}"
        ]
        state["model"]["map-entry-states"] = states
        state["model"]["map-geometry"] = geometry
        state["model"]["map-entries"] = [
            item
            for item in state["model"]["map-entries"]
            if item["name"] != name
        ]
        state["model"]["map-z-order"] = z_order
        state["selected-entry"] = None
        state["status"] = f"Removed missing map node {name}."
        effects.extend(
            [
                {
                    "type": "WRITE_MAP_ENTRY_STATES",
                    "folder": state["folder"],
                    "states": states,
                },
                {
                    "type": "WRITE_MAP_GEOMETRY",
                    "folder": state["folder"],
                    "geometry": geometry,
                },
                {
                    "type": "WRITE_MAP_Z_ORDER",
                    "folder": state["folder"],
                    "z-order": z_order,
                },
                {"type": "PROJECT_DIRECTORY_MAP"},
                {"type": "PROJECT_STATUS"},
            ]
        )

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

    elif name == "GROUP_GEOMETRY_COMMITTED":
        entry_geometry = deepcopy(state["model"]["map-geometry"])
        texts = deepcopy(state["model"]["map-texts"])
        images = deepcopy(state["model"]["map-images"])
        text_by_id = {item["id"]: item for item in texts}
        image_by_id = {item["id"]: item for item in images}

        for key, geometry in event["geometry"].items():
            kind, identity = key.split(":", 1)
            if kind == "entry":
                entry_geometry[identity] = geometry
            elif kind == "text" and identity in text_by_id:
                text_by_id[identity].update(geometry)
            elif kind == "image" and identity in image_by_id:
                image_by_id[identity].update(geometry)

        state["model"]["map-geometry"] = entry_geometry
        state["model"]["map-texts"] = texts
        state["model"]["map-images"] = images
        effects.extend(
            [
                {
                    "type": "WRITE_MAP_GEOMETRY",
                    "folder": state["folder"],
                    "geometry": entry_geometry,
                },
                {
                    "type": "WRITE_MAP_TEXTS",
                    "folder": state["folder"],
                    "texts": texts,
                },
                {
                    "type": "WRITE_MAP_IMAGES",
                    "folder": state["folder"],
                    "images": images,
                },
                {"type": "PROJECT_MAP"},
            ]
        )

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
        state["group-selection"] = []
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SELECT_MAP_TEXT":
        state["selected-entry"] = None
        state["selected-text"] = event["text-id"]
        state["selected-image"] = None
        state["group-selection"] = []
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SELECT_MAP_IMAGE":
        state["selected-entry"] = None
        state["selected-text"] = None
        state["selected-image"] = event["image-id"]
        state["group-selection"] = []
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SET_GROUP_SELECTION":
        state["selected-entry"] = None
        state["selected-text"] = None
        state["selected-image"] = None
        state["group-selection"] = list(event["keys"])
        effects.append({"type": "PROJECT_MAP"})

    elif name == "CLEAR_SELECTION":
        state["selected-entry"] = None
        state["selected-text"] = None
        state["selected-image"] = None
        state["group-selection"] = []
        effects.append({"type": "PROJECT_MAP"})

    elif name == "SET_STATUS":
        state["status"] = event["text"]
        effects.append({"type": "PROJECT_STATUS"})

    else:
        raise ValueError(f"Unknown semantic event: {name}")

    return state, effects
