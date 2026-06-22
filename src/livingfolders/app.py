"""Tkinter control panel and projection for Living Folders."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageGrab, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

from .core import (
    PRESENTATION_MODES,
    delete_immediate_file,
    get_cached_image_path,
    import_clipboard_image,
    import_image_file,
    inspect_folder,
    resolve_image_asset_path,
    resolve_navigation_target,
    save_buttons,
    save_code_trust,
    save_command_annotations,
    save_map_geometry,
    save_map_images,
    save_map_texts,
    save_map_z_order,
    save_presentation,
)
from .discrete import initial_state, reduce
from . import runtime


COLORS = {
    "background": "#15191d",
    "panel": "#20262c",
    "panel-2": "#293139",
    "text": "#edf1f4",
    "quiet": "#98a4ad",
    "accent": "#79c9ff",
    "selected": "#ffffff",
    "folder": "#d9ad3c",
    "executable": "#c85656",
    "text-file": "#4d82c4",
    "json": "#62b8cf",
    "image": "#9c6ac4",
    "file": "#727d86",
}

MODE_LABELS = {
    "directory-map": "Directory Map",
    "project-root": "Project Root",
    "control-panel": "Control Panel",
    "workbench": "Workbench",
    "factory": "Factory",
    "library": "Library",
    "gallery": "Gallery",
    "inbox": "Inbox",
    "vault": "Vault",
    "warehouse": "Warehouse",
    "hallway": "Hallway",
    "ruin": "Ruin",
}

g = {
    "tk": None,
    "widgets": {},
    "state": initial_state(),
    "projecting": False,
    "work-queue": queue.Queue(),
    "result-queue": queue.Queue(),
    "closing": False,
    "map-items": {},
    "map-item-entry": {},
    "map-handles": set(),
    "map-text-items": {},
    "map-item-text-id": {},
    "map-text-handles": set(),
    "map-image-items": {},
    "map-item-image-id": {},
    "map-image-handles": set(),
    "map-image-photos": {},
    "marquee-item": None,
    "marquee-glow-items": [],
    "interaction": None,
    "instance": None,
}


def run(path):
    """Create the two-thread Tkinter application and open the requested folder."""
    instance = runtime.acquire_instance()
    if instance is None:
        runtime.send_summons(path)
        return

    g["instance"] = instance
    try:
        build_window()
        runtime.publish_window_handle(instance, g["tk"].winfo_id())
        start_worker()
        dispatch({"type": "NAVIGATE", "path": str(path), "remember": False})
        poll_worker_results()
        poll_runtime_inbox()
        g["tk"].deiconify()
        g["tk"].mainloop()
    finally:
        runtime.release_instance(instance)
        g["instance"] = None


def build_window():
    root = TkinterDnD.Tk()
    root.withdraw()
    root.title(f"Living Folders  [{runtime.WINDOW_TOKEN}]")
    root.geometry("1240x820")
    root.minsize(860, 600)
    root.option_add("*tearOff", 0)
    root.protocol("WM_DELETE_WINDOW", close_application)
    root.bind("<Control-v>", handle_global_paste)
    root.bind("<Control-V>", handle_global_paste)
    root.configure(bg=COLORS["background"])
    root.columnconfigure(0, weight=1)
    root.rowconfigure(2, weight=1)
    g["tk"] = root

    build_styles()
    build_navigation_bar()
    build_control_strip()
    build_projection_area()
    build_status_bar()


def build_styles():
    style = ttk.Style(g["tk"])
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10))
    style.configure(
        "Panel.TFrame",
        background=COLORS["panel"],
    )
    style.configure(
        "Living.TButton",
        padding=(8, 5),
        background=COLORS["panel-2"],
        foreground=COLORS["text"],
        borderwidth=0,
    )
    style.map("Living.TButton", background=[("active", "#3a4650")])
    style.configure(
        "Counter.TButton",
        padding=(10, 7),
        background="#303941",
        foreground=COLORS["text"],
        borderwidth=1,
    )
    style.map(
        "Counter.TButton",
        background=[("active", "#46535d"), ("disabled", "#252a2e")],
        foreground=[("disabled", "#68737b")],
    )
    style.configure(
        "Living.TCheckbutton",
        background=COLORS["panel"],
        foreground=COLORS["text"],
    )
    style.map("Living.TCheckbutton", background=[("active", COLORS["panel"])])
    style.configure(
        "Living.TCombobox",
        fieldbackground="#111518",
        background=COLORS["panel-2"],
        foreground=COLORS["text"],
        arrowcolor=COLORS["text"],
    )


def build_navigation_bar():
    bar = ttk.Frame(g["tk"], style="Panel.TFrame", padding=(10, 9))
    bar.grid(row=0, column=0, sticky="ew")
    bar.columnconfigure(4, weight=1)

    buttons = [
        ("back", "←", handle_back),
        ("up", "↑", handle_up),
        ("refresh", "↻", handle_refresh),
        ("choose", "Choose folder", handle_choose_folder),
    ]
    for column, (name, text, handler) in enumerate(buttons):
        widget = ttk.Button(bar, text=text, command=handler, style="Living.TButton")
        widget.grid(row=0, column=column, padx=(0, 6))
        g["widgets"][name] = widget

    path_var = tk.StringVar()
    entry = ttk.Entry(bar, textvariable=path_var, font=("Cascadia Mono", 9))
    entry.grid(row=0, column=4, sticky="ew", padx=(2, 8))
    entry.bind("<Return>", handle_path_entered)
    g["widgets"]["path-var"] = path_var
    g["widgets"]["path-entry"] = entry

    explorer = ttk.Button(
        bar,
        text="Explorer",
        command=handle_open_explorer,
        style="Living.TButton",
    )
    explorer.grid(row=0, column=5, padx=(0, 6))
    g["widgets"]["explorer"] = explorer

    shell = ttk.Button(
        bar,
        text="Shell",
        command=handle_open_shell,
        style="Living.TButton",
    )
    shell.grid(row=0, column=6)
    g["widgets"]["shell"] = shell


def build_control_strip():
    strip = ttk.Frame(g["tk"], style="Panel.TFrame", padding=(12, 7, 12, 10))
    strip.grid(row=1, column=0, sticky="ew")
    strip.columnconfigure(5, weight=1)

    ttk.Label(
        strip,
        text="PRESENTATION",
        background=COLORS["panel"],
        foreground=COLORS["accent"],
        font=("Segoe UI Semibold", 9),
    ).grid(row=0, column=0, padx=(0, 8))

    mode_var = tk.StringVar()
    mode = ttk.Combobox(
        strip,
        textvariable=mode_var,
        state="readonly",
        width=24,
        style="Living.TCombobox",
    )
    mode.grid(row=0, column=1, padx=(0, 10))
    mode.bind("<<ComboboxSelected>>", handle_presentation_selected)
    g["widgets"]["mode-var"] = mode_var
    g["widgets"]["mode"] = mode

    inferred_var = tk.StringVar()
    ttk.Label(
        strip,
        textvariable=inferred_var,
        background=COLORS["panel"],
        foreground=COLORS["quiet"],
    ).grid(row=0, column=2, padx=(0, 16))
    g["widgets"]["inferred-var"] = inferred_var

    trust_var = tk.BooleanVar()
    trust = ttk.Checkbutton(
        strip,
        text="I trust runnable code in this folder",
        variable=trust_var,
        command=handle_trust_changed,
        style="Living.TCheckbutton",
    )
    trust.grid(row=0, column=3, padx=(0, 14))
    g["widgets"]["trust-var"] = trust_var
    g["widgets"]["trust"] = trust

    ttk.Button(
        strip,
        text="Edit buttons…",
        command=handle_edit_buttons,
        style="Living.TButton",
    ).grid(row=0, column=4)


def build_projection_area():
    body = tk.Frame(g["tk"], bg=COLORS["background"])
    body.grid(row=2, column=0, sticky="nsew")
    body.columnconfigure(0, weight=1)
    body.rowconfigure(0, weight=1)
    g["widgets"]["body"] = body


def build_status_bar():
    bar = ttk.Frame(g["tk"], style="Panel.TFrame", padding=(10, 6))
    bar.grid(row=3, column=0, sticky="ew")
    bar.columnconfigure(0, weight=1)
    status_var = tk.StringVar(value="Ready.")
    ttk.Label(
        bar,
        textvariable=status_var,
        background=COLORS["panel"],
        foreground=COLORS["quiet"],
    ).grid(row=0, column=0, sticky="w")
    g["widgets"]["status-var"] = status_var

    output = ttk.Button(
        bar,
        text="Command output…",
        command=show_command_output,
        style="Living.TButton",
    )
    output.grid(row=0, column=1)
    g["widgets"]["command-output-button"] = output
    g["widgets"]["command-output"] = "No command has run."


def dispatch(event):
    state, effects = reduce(g["state"], event)
    g["state"].clear()
    g["state"].update(state)
    for effect in effects:
        route_effect(effect)


def route_effect(effect):
    name = effect["type"]

    if name == "LOAD_FOLDER":
        load_folder_effect(effect)
    elif name == "SAVE_PRESENTATION":
        save_presentation(effect["folder"], effect["mode"])
        dispatch({"type": "REFRESH"})
    elif name == "SAVE_CODE_TRUST":
        save_code_trust(effect["folder"], effect["trusted"])
        dispatch({"type": "REFRESH"})
    elif name == "WRITE_BUTTONS":
        save_buttons(effect["folder"], effect["buttons"])
        dispatch({"type": "REFRESH"})
    elif name == "WRITE_COMMAND_ANNOTATIONS":
        save_command_annotations(effect["folder"], effect["annotations"])
        dispatch({"type": "REFRESH"})
    elif name == "DELETE_FILE":
        delete_file_effect(effect)
    elif name == "WRITE_MAP_GEOMETRY":
        save_map_geometry(effect["folder"], effect["geometry"])
    elif name == "WRITE_MAP_TEXTS":
        save_map_texts(effect["folder"], effect["texts"])
    elif name == "WRITE_MAP_IMAGES":
        save_map_images(effect["folder"], effect["images"])
    elif name == "WRITE_MAP_Z_ORDER":
        save_map_z_order(effect["folder"], effect["z-order"])
    elif name == "PROJECT":
        project_everything()
    elif name == "PROJECT_ACTIONS":
        project_actions()
    elif name == "PROJECT_MAP":
        project_map()
    elif name == "PROJECT_STATUS":
        project_status()
    else:
        raise ValueError(f"Unknown effect: {name}")


def load_folder_effect(effect):
    try:
        model = inspect_folder(effect["path"])
    except ValueError:
        restore_path_entry()
        dispatch({"type": "SET_STATUS", "text": "That path was not a folder; stayed here."})
        return
    dispatch(
        {
            "type": "FOLDER_LOADED",
            "model": model,
            "remember": effect["remember"],
            "status": f"Opened {model['folder']}",
        }
    )


def delete_file_effect(effect):
    try:
        delete_immediate_file(effect["folder"], effect["path"])
    except (OSError, ValueError) as error:
        dispatch({"type": "SET_STATUS", "text": str(error)})
        return
    dispatch({"type": "REFRESH"})


def project_everything():
    g["projecting"] = True
    model = g["state"]["model"]
    path = model["folder"]
    if g["instance"]:
        runtime.publish_current_folder(g["instance"], path)
    g["widgets"]["path-var"].set(path)
    g["widgets"]["back"].configure(
        state="normal" if g["state"]["back-stack"] else "disabled"
    )
    g["widgets"]["up"].configure(
        state="normal" if Path(path).parent != Path(path) else "disabled"
    )

    auto_label = auto_mode_label(model["inferred-presentation"])
    values = [auto_label] + [MODE_LABELS[mode] for mode in PRESENTATION_MODES]
    g["widgets"]["mode"].configure(values=values)
    if model["explicit-presentation"]:
        selected = MODE_LABELS.get(
            model["explicit-presentation"],
            model["explicit-presentation"].replace("-", " ").title(),
        )
    else:
        selected = auto_label
    g["widgets"]["mode-var"].set(selected)
    g["widgets"]["inferred-var"].set(
        f"inferred: {MODE_LABELS.get(model['inferred-presentation'], model['inferred-presentation'])}"
    )
    g["widgets"]["trust-var"].set(g["state"]["trust-code"])
    g["projecting"] = False

    replace_body()
    project_status()


def replace_body():
    body = g["widgets"]["body"]
    for child in body.winfo_children():
        child.destroy()
    g["map-items"].clear()
    g["map-item-entry"].clear()
    g["map-handles"].clear()
    g["map-text-items"].clear()
    g["map-item-text-id"].clear()
    g["map-text-handles"].clear()
    g["map-image-items"].clear()
    g["map-item-image-id"].clear()
    g["map-image-handles"].clear()
    g["map-image-photos"].clear()
    g["marquee-item"] = None
    g["marquee-glow-items"].clear()

    model = g["state"]["model"]
    if model["active-presentation"] == "directory-map":
        build_directory_map(body)
    else:
        build_control_panel(body)


def build_control_panel(parent):
    panel = tk.Frame(parent, bg=COLORS["background"], padx=18, pady=16)
    panel.grid(row=0, column=0, sticky="nsew")
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(3, weight=1)
    model = g["state"]["model"]

    tk.Label(
        panel,
        text=model["title"],
        bg=COLORS["background"],
        fg=COLORS["text"],
        font=("Segoe UI Semibold", 24),
        anchor="w",
    ).grid(row=0, column=0, sticky="ew")
    tk.Label(
        panel,
        text=model["purpose"],
        bg=COLORS["background"],
        fg=COLORS["quiet"],
        font=("Segoe UI", 11),
        anchor="w",
    ).grid(row=1, column=0, sticky="ew", pady=(2, 12))

    actions = tk.Frame(panel, bg=COLORS["background"])
    actions.grid(row=2, column=0, sticky="ew", pady=(0, 12))
    g["widgets"]["actions"] = actions
    project_actions()

    tree = ttk.Treeview(
        panel,
        columns=("kind", "size"),
        show="tree headings",
        selectmode="browse",
    )
    tree.heading("#0", text="Contents")
    tree.heading("kind", text="Kind")
    tree.heading("size", text="Size")
    tree.column("#0", width=620)
    tree.column("kind", width=130, anchor="w")
    tree.column("size", width=100, anchor="e")
    tree.grid(row=3, column=0, sticky="nsew")
    tree.bind("<Double-1>", handle_tree_double_click)
    g["widgets"]["tree"] = tree
    g["widgets"]["tree-entries"] = {}

    for entry in model["entries"]:
        item = tree.insert(
            "",
            "end",
            text=entry["name"],
            values=(entry["visual-kind"], format_size(entry["size"])),
            tags=(entry["visual-kind"],),
        )
        g["widgets"]["tree-entries"][item] = entry

    for kind, color in visual_colors().items():
        tree.tag_configure(kind, foreground=color)


def project_actions():
    actions = g["widgets"].get("actions")
    if not actions or not actions.winfo_exists():
        return
    for child in actions.winfo_children():
        child.destroy()

    model = g["state"]["model"]
    buttons = model["buttons"] + model["detected-buttons"]
    for number, button in enumerate(buttons):
        widget = ttk.Button(
            actions,
            text=button["label"],
            command=lambda item=button: activate_button(item),
            style="Counter.TButton",
        )
        if button["kind"] == "command" and not g["state"]["trust-code"]:
            widget.configure(state="disabled")
        widget.grid(row=number // 7, column=number % 7, padx=(0, 5), pady=(0, 5))

    if not buttons:
        tk.Label(
            actions,
            text="No folder buttons yet. Use “Edit buttons…” to add navigation or commands.",
            bg=COLORS["background"],
            fg=COLORS["quiet"],
        ).grid(row=0, column=0, sticky="w")


def build_directory_map(parent):
    frame = tk.Frame(parent, bg=COLORS["background"])
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(1, weight=1)

    header = tk.Frame(frame, bg=COLORS["background"], padx=12, pady=8)
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)

    actions = tk.Frame(header, bg=COLORS["background"])
    actions.grid(row=0, column=0, sticky="ew")
    g["widgets"]["actions"] = actions
    project_actions()
    ttk.Button(
        header,
        text="＋ Image…",
        command=handle_add_image,
        style="Living.TButton",
    ).grid(row=0, column=1, sticky="e")
    ttk.Button(
        header,
        text="From Clipboard",
        command=handle_paste_image,
        style="Living.TButton",
    ).grid(row=0, column=2, sticky="e", padx=(6, 0))

    canvas = tk.Canvas(
        frame,
        bg="#101417",
        highlightthickness=0,
        scrollregion=(0, 0, 1800, 1200),
    )
    xbar = ttk.Scrollbar(frame, orient="horizontal", command=canvas.xview)
    ybar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
    canvas.grid(row=1, column=0, sticky="nsew")
    ybar.grid(row=1, column=1, sticky="ns")
    xbar.grid(row=2, column=0, sticky="ew")
    canvas.bind("<ButtonPress-1>", handle_map_press)
    canvas.bind("<B1-Motion>", handle_map_motion)
    canvas.bind("<ButtonRelease-1>", handle_map_release)
    canvas.bind("<Double-Button-1>", handle_map_double_click)
    canvas.bind("<Delete>", handle_delete_key)
    canvas.bind("<Prior>", handle_page_up)
    canvas.bind("<Next>", handle_page_down)
    canvas.bind("<Control-v>", handle_paste_image)
    canvas.bind("<Control-V>", handle_paste_image)
    canvas.drop_target_register(DND_FILES)
    canvas.dnd_bind("<<Drop>>", handle_image_drop)
    g["widgets"]["map"] = canvas
    project_map()


def project_map():
    canvas = g["widgets"].get("map")
    if not canvas or not canvas.winfo_exists():
        return
    canvas.delete("all")
    g["map-items"].clear()
    g["map-item-entry"].clear()
    g["map-handles"].clear()
    g["map-text-items"].clear()
    g["map-item-text-id"].clear()
    g["map-text-handles"].clear()
    g["map-image-items"].clear()
    g["map-item-image-id"].clear()
    g["map-image-handles"].clear()
    g["map-image-photos"].clear()
    g["marquee-item"] = None
    g["marquee-glow-items"].clear()
    model = g["state"]["model"]

    entries = {item["name"]: item for item in model["entries"]}
    texts = {item["id"]: item for item in model["map-texts"]}
    images = {item["id"]: item for item in model["map-images"]}
    entry_numbers = {
        item["name"]: number for number, item in enumerate(model["entries"])
    }

    for key in model["map-z-order"]:
        kind, identity = key.split(":", 1)
        if kind == "entry" and identity in entries:
            geometry = model["map-geometry"].get(
                identity,
                default_geometry(entry_numbers[identity]),
            )
            draw_map_entry(canvas, entries[identity], geometry)
        elif kind == "text" and identity in texts:
            draw_map_text(canvas, texts[identity])
        elif kind == "image" and identity in images:
            draw_map_image(canvas, images[identity])
    draw_group_selection_glow()


def draw_map_entry(canvas, entry, geometry):
    x = geometry["x"]
    y = geometry["y"]
    width = geometry["width"]
    height = geometry["height"]
    key = f"entry:{entry['name']}"
    group_selected = key in g["state"]["group-selection"]
    selected = g["state"]["selected-entry"] == entry["name"] or group_selected
    fill = visual_colors()[entry["visual-kind"]]
    outline = COLORS["selected"] if selected else "#111111"
    line_width = 3 if selected else 1

    rectangle = canvas.create_rectangle(
        x,
        y,
        x + width,
        y + height,
        fill=fill,
        outline=outline,
        width=line_width,
    )
    text = canvas.create_text(
        x + 9,
        y + 9,
        text=entry["name"],
        anchor="nw",
        fill="#101010",
        font=("Segoe UI Semibold", 10),
        width=max(40, width - 18),
    )
    items = [rectangle, text]
    if not group_selected:
        handle = canvas.create_rectangle(
            x + width - 12,
            y + height - 12,
            x + width,
            y + height,
            fill="#111111",
            outline="",
        )
        items.append(handle)
        g["map-handles"].add(handle)
    g["map-items"][entry["name"]] = items
    for item in items:
        g["map-item-entry"][item] = entry["name"]


def draw_map_text(canvas, text_item):
    if not text_item["labelled-region"]:
        item = canvas.create_text(
            text_item["x"],
            text_item["y"],
            text=text_item["text"],
            anchor="nw",
            justify=text_item["alignment"],
            width=420,
            fill=map_text_color(text_item["color"]),
            font=("Segoe UI", map_text_font_size(text_item["font-size"])),
        )
        items = [item]
    else:
        items = draw_labelled_region(canvas, text_item)

    g["map-text-items"][text_item["id"]] = items
    for item in items:
        g["map-item-text-id"][item] = text_item["id"]


def draw_labelled_region(canvas, text_item):
    x = text_item["x"]
    y = text_item["y"]
    width = text_item["width"]
    height = text_item["height"]
    color = map_text_color(text_item["color"])
    group_selected = f"text:{text_item['id']}" in g["state"]["group-selection"]
    line_color = color
    line_width = 1 if text_item["region-line-width"] == "thin" else 2
    label_x, anchor = labelled_region_label_position(text_item)

    label = canvas.create_text(
        label_x,
        y,
        text=text_item["text"],
        anchor=anchor,
        justify=text_item["alignment"],
        width=max(40, width - 24),
        fill=color,
        font=("Segoe UI", map_text_font_size(text_item["font-size"])),
    )
    bbox = canvas.bbox(label)
    label_left = max(x, bbox[0] - 7)
    label_right = min(x + width, bbox[2] + 7)
    top_y = int((bbox[1] + bbox[3]) / 2)
    bottom_y = y + height

    left = canvas.create_line(x, top_y, x, bottom_y, fill=line_color, width=line_width)
    right = canvas.create_line(
        x + width,
        top_y,
        x + width,
        bottom_y,
        fill=line_color,
        width=line_width,
    )
    bottom = canvas.create_line(
        x,
        bottom_y,
        x + width,
        bottom_y,
        fill=line_color,
        width=line_width,
    )
    top_left = canvas.create_line(
        x,
        top_y,
        label_left,
        top_y,
        fill=line_color,
        width=line_width,
    )
    top_right = canvas.create_line(
        label_right,
        top_y,
        x + width,
        top_y,
        fill=line_color,
        width=line_width,
    )
    items = [left, right, bottom, top_left, top_right, label]
    if not group_selected:
        handle = canvas.create_rectangle(
            x + width - 14,
            bottom_y - 14,
            x + width,
            bottom_y,
            fill=line_color,
            outline="#111111",
        )
        items.append(handle)
        g["map-text-handles"].add(handle)
    return items


def labelled_region_label_position(text_item):
    if text_item["alignment"] == "center":
        return text_item["x"] + text_item["width"] / 2, "n"
    if text_item["alignment"] == "right":
        return text_item["x"] + text_item["width"] - 12, "ne"
    return text_item["x"] + 12, "nw"


def draw_map_image(canvas, image_item):
    try:
        cache_path = get_cached_image_path(g["state"]["folder"], image_item)
        with Image.open(cache_path) as image:
            photo = ImageTk.PhotoImage(image.copy())
    except ValueError as error:
        dispatch({"type": "SET_STATUS", "text": str(error)})
        return

    x = image_item["x"]
    y = image_item["y"]
    width = image_item["width"]
    height = image_item["height"]
    key = f"image:{image_item['id']}"
    group_selected = key in g["state"]["group-selection"]
    selected = g["state"]["selected-image"] == image_item["id"] or group_selected
    border = canvas.create_rectangle(
        x,
        y,
        x + width,
        y + height,
        fill="#080a0c",
        outline=COLORS["selected"] if selected else "#3c454d",
        width=3 if selected else 1,
    )
    picture = canvas.create_image(x, y, image=photo, anchor="nw")
    items = [border, picture]
    if not group_selected:
        handle = canvas.create_rectangle(
            x + width - 14,
            y + height - 14,
            x + width,
            y + height,
            fill="#ffffff",
            outline="#111111",
        )
        items.append(handle)
        g["map-image-handles"].add(handle)
    g["map-image-items"][image_item["id"]] = items
    g["map-image-photos"][image_item["id"]] = photo
    for item in items:
        g["map-item-image-id"][item] = image_item["id"]


def draw_group_selection_glow():
    canvas = g["widgets"].get("map")
    if not canvas:
        return
    for key in g["state"]["group-selection"]:
        bbox = map_element_bbox(key)
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        canvas.create_rectangle(
            x1 - 4,
            y1 - 4,
            x2 + 4,
            y2 + 4,
            outline=COLORS["accent"],
            width=3,
            dash=(5, 3),
            tags=("group-selection-glow",),
        )


def refresh_group_selection_glow():
    canvas = g["widgets"]["map"]
    canvas.delete("group-selection-glow")
    draw_group_selection_glow()


def top_map_hit(items):
    for item in reversed(items):
        if item in g["map-item-image-id"]:
            return item, f"image:{g['map-item-image-id'][item]}"
        if item in g["map-item-text-id"]:
            return item, f"text:{g['map-item-text-id'][item]}"
        if item in g["map-item-entry"]:
            return item, f"entry:{g['map-item-entry'][item]}"
    return None, None


def map_element_bbox(key):
    kind, identity = key.split(":", 1)
    if kind == "entry" and identity in g["map-items"]:
        return g["widgets"]["map"].bbox(*g["map-items"][identity])
    if kind == "text" and identity in g["map-text-items"]:
        return g["widgets"]["map"].bbox(*g["map-text-items"][identity])
    if kind == "image" and identity in g["map-image-items"]:
        return g["widgets"]["map"].bbox(*g["map-image-items"][identity])
    return None


def current_map_element_geometry(key):
    kind, identity = key.split(":", 1)
    if kind == "entry":
        return current_canvas_geometry(identity)
    if kind == "text":
        return current_canvas_text_geometry(identity)
    if kind == "image":
        return current_canvas_image_geometry(identity)
    raise ValueError(f"Unknown map element kind: {kind}")


def position_map_element(key, geometry):
    kind, identity = key.split(":", 1)
    if kind == "entry":
        position_canvas_entry(identity, geometry)
    elif kind == "text":
        position_canvas_text(identity, geometry)
    elif kind == "image":
        position_canvas_image(identity, geometry)
    else:
        raise ValueError(f"Unknown map element kind: {kind}")


def update_marquee_preview(interaction):
    canvas = g["widgets"]["map"]
    clear_marquee_preview()
    x1, y1, x2, y2 = normalized_rectangle(
        interaction["start-x"],
        interaction["start-y"],
        interaction["current-x"],
        interaction["current-y"],
    )
    g["marquee-item"] = canvas.create_rectangle(
        x1,
        y1,
        x2,
        y2,
        outline=COLORS["accent"],
        width=2,
        dash=(6, 4),
        fill="#19364a",
        stipple="gray50",
    )
    candidates = []
    for key in g["state"]["model"]["map-z-order"]:
        bbox = map_element_bbox(key)
        if bbox and rectangles_overlap((x1, y1, x2, y2), bbox):
            candidates.append(key)
            glow = canvas.create_rectangle(
                bbox[0] - 5,
                bbox[1] - 5,
                bbox[2] + 5,
                bbox[3] + 5,
                outline="#b8ebff",
                width=4,
            )
            g["marquee-glow-items"].append(glow)
    interaction["candidates"] = candidates


def clear_marquee_preview():
    canvas = g["widgets"].get("map")
    if not canvas:
        return
    if g["marquee-item"]:
        canvas.delete(g["marquee-item"])
        g["marquee-item"] = None
    for item in g["marquee-glow-items"]:
        canvas.delete(item)
    g["marquee-glow-items"].clear()


def normalized_rectangle(x1, y1, x2, y2):
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def rectangles_overlap(first, second):
    return not (
        first[2] < second[0]
        or first[0] > second[2]
        or first[3] < second[1]
        or first[1] > second[3]
    )


def default_geometry(number):
    column = number % 5
    row = number // 5
    return {
        "x": 30 + column * 175,
        "y": 30 + row * 110,
        "width": 150,
        "height": 78,
    }


def handle_map_press(event):
    canvas = g["widgets"]["map"]
    canvas.focus_set()
    x = canvas.canvasx(event.x)
    y = canvas.canvasy(event.y)
    items = canvas.find_overlapping(
        x,
        y,
        x,
        y,
    )
    item, key = top_map_hit(items)

    if key and key in g["state"]["group-selection"]:
        origins = {
            selected: current_map_element_geometry(selected)
            for selected in g["state"]["group-selection"]
        }
        g["interaction"] = {
            "kind": "group",
            "pressed-key": key,
            "start-x": x,
            "start-y": y,
            "origins": origins,
            "preview": origins,
            "changed": False,
        }
        return

    if key and key.startswith("image:"):
        image_id = key.split(":", 1)[1]
        is_resize = item in g["map-image-handles"]
        dispatch({"type": "SELECT_MAP_IMAGE", "image-id": image_id})
        geometry = current_canvas_image_geometry(image_id)
        g["interaction"] = {
            "kind": "image",
            "image-id": image_id,
            "mode": "resize" if is_resize else "move",
            "start-x": x,
            "start-y": y,
            "origin": geometry,
            "preview": geometry.copy(),
            "changed": False,
        }
        return

    if key and key.startswith("text:"):
        text_id = key.split(":", 1)[1]
        is_resize = item in g["map-text-handles"]
        dispatch({"type": "SELECT_MAP_TEXT", "text-id": text_id})
        geometry = current_canvas_text_geometry(text_id)
        g["interaction"] = {
            "kind": "text",
            "text-id": text_id,
            "mode": "resize" if is_resize else "move",
            "start-x": x,
            "start-y": y,
            "origin": geometry,
            "preview": geometry.copy(),
            "changed": False,
        }
        return

    if key and key.startswith("entry:"):
        name = key.split(":", 1)[1]
        is_resize = item in g["map-handles"]
        geometry = current_canvas_geometry(name)
        dispatch({"type": "SELECT_ENTRY", "entry-name": name})
        g["interaction"] = {
            "kind": "entry",
            "entry-name": name,
            "mode": "resize" if is_resize else "move",
            "start-x": x,
            "start-y": y,
            "origin": geometry,
            "preview": geometry.copy(),
            "changed": False,
        }
        return

    dispatch({"type": "CLEAR_SELECTION"})
    g["interaction"] = {
        "kind": "marquee",
        "start-x": x,
        "start-y": y,
        "current-x": x,
        "current-y": y,
        "candidates": [],
        "changed": False,
    }


def handle_map_motion(event):
    interaction = g["interaction"]
    if not interaction:
        return
    canvas = g["widgets"]["map"]
    dx = canvas.canvasx(event.x) - interaction["start-x"]
    dy = canvas.canvasy(event.y) - interaction["start-y"]
    if interaction["kind"] == "marquee":
        interaction["current-x"] = canvas.canvasx(event.x)
        interaction["current-y"] = canvas.canvasy(event.y)
        interaction["changed"] = True
        update_marquee_preview(interaction)
        return

    if interaction["kind"] == "group":
        preview = {}
        for key, origin in interaction["origins"].items():
            geometry = {
                **origin,
                "x": max(0, int(origin["x"] + dx)),
                "y": max(0, int(origin["y"] + dy)),
            }
            preview[key] = geometry
            position_map_element(key, geometry)
        refresh_group_selection_glow()
        interaction["preview"] = preview
        interaction["changed"] = True
        return

    origin = interaction["origin"]
    if interaction["kind"] == "text":
        if interaction["mode"] == "resize":
            preview = {
                **origin,
                "width": max(120, int(origin["width"] + dx)),
                "height": max(70, int(origin["height"] + dy)),
            }
        else:
            preview = {
                **origin,
                "x": max(0, int(origin["x"] + dx)),
                "y": max(0, int(origin["y"] + dy)),
            }
        interaction["preview"] = preview
        interaction["changed"] = True
        position_canvas_text(interaction["text-id"], preview)
        return

    if interaction["kind"] == "image":
        if interaction["mode"] == "move":
            preview = {
                **origin,
                "x": max(0, int(origin["x"] + dx)),
                "y": max(0, int(origin["y"] + dy)),
            }
        else:
            preview = {
                **origin,
                "width": max(24, int(origin["width"] + dx)),
                "height": max(24, int(origin["height"] + dy)),
            }
        interaction["preview"] = preview
        interaction["changed"] = True
        position_canvas_image(interaction["image-id"], preview)
        return

    if interaction["mode"] == "move":
        preview = {
            **origin,
            "x": max(0, int(origin["x"] + dx)),
            "y": max(0, int(origin["y"] + dy)),
        }
    else:
        preview = {
            **origin,
            "width": max(70, int(origin["width"] + dx)),
            "height": max(44, int(origin["height"] + dy)),
        }
    interaction["preview"] = preview
    interaction["changed"] = True
    position_canvas_entry(interaction["entry-name"], preview)


def handle_map_release(_event):
    interaction = g["interaction"]
    g["interaction"] = None
    if not interaction:
        return
    if interaction["kind"] == "marquee":
        clear_marquee_preview()
        if interaction["changed"]:
            dispatch(
                {
                    "type": "SET_GROUP_SELECTION",
                    "keys": interaction["candidates"],
                }
            )
        return
    if interaction["kind"] == "group":
        if interaction["changed"]:
            dispatch(
                {
                    "type": "GROUP_GEOMETRY_COMMITTED",
                    "geometry": interaction["preview"],
                }
            )
        else:
            select_map_key(interaction["pressed-key"])
        return
    if interaction["kind"] == "text":
        if interaction["changed"]:
            dispatch(
                {
                    "type": "MAP_TEXT_GEOMETRY_COMMITTED",
                    "text-id": interaction["text-id"],
                    "geometry": interaction["preview"],
                }
            )
        return
    if interaction["kind"] == "image":
        if interaction["changed"]:
            dispatch(
                {
                    "type": "MAP_IMAGE_GEOMETRY_COMMITTED",
                    "image-id": interaction["image-id"],
                    "geometry": interaction["preview"],
                }
            )
        return
    if interaction["changed"]:
        dispatch(
            {
                "type": "MAP_GEOMETRY_COMMITTED",
                "entry-name": interaction["entry-name"],
                "geometry": interaction["preview"],
            }
        )
    else:
        dispatch(
            {
                "type": "SELECT_ENTRY",
                "entry-name": interaction["entry-name"],
            }
        )


def handle_map_double_click(event):
    canvas = g["widgets"]["map"]
    x = int(canvas.canvasx(event.x))
    y = int(canvas.canvasy(event.y))
    items = canvas.find_overlapping(
        x,
        y,
        x,
        y,
    )
    for item in reversed(items):
        if item in g["map-item-image-id"]:
            image_item = find_map_image(g["map-item-image-id"][item])
            open_os_path(resolve_image_asset_path(g["state"]["folder"], image_item))
            return
        if item in g["map-item-text-id"]:
            text_item = find_map_text(g["map-item-text-id"][item])
            edited = edit_map_text_dialog(text_item)
            if edited:
                dispatch({"type": "UPSERT_MAP_TEXT", "text-item": edited})
            return
        if item in g["map-item-entry"]:
            open_entry_by_name(g["map-item-entry"][item])
            return
    created = edit_map_text_dialog(
        {
            "id": str(uuid.uuid4()),
            "text": "",
            "x": x,
            "y": y,
            "alignment": "left",
            "font-size": "medium",
            "color": "white",
            "labelled-region": False,
            "region-line-width": "thick",
            "width": 320,
            "height": 180,
        }
    )
    if created and created["text"].strip():
        dispatch({"type": "UPSERT_MAP_TEXT", "text-item": created})


def handle_add_image():
    path = filedialog.askopenfilename(
        parent=g["tk"],
        initialdir=g["state"]["folder"],
        title="Add image to Directory Map",
        filetypes=[
            ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
            ("All files", "*.*"),
        ],
    )
    if not path:
        return
    import_image_paths([path], 80, 80)


def handle_image_drop(event):
    canvas = g["widgets"]["map"]
    x = int(canvas.canvasx(event.x_root - canvas.winfo_rootx()))
    y = int(canvas.canvasy(event.y_root - canvas.winfo_rooty()))
    paths = list(g["tk"].tk.splitlist(event.data))
    import_image_paths(paths, x, y)
    return getattr(event, "action", "copy")


def handle_paste_image(_event=None):
    canvas = g["widgets"]["map"]
    x = int(canvas.canvasx(max(40, canvas.winfo_width() // 2)))
    y = int(canvas.canvasy(max(40, canvas.winfo_height() // 2)))
    content = ImageGrab.grabclipboard()
    if isinstance(content, Image.Image):
        try:
            image_item = import_clipboard_image(g["state"]["folder"], content, x, y)
        except (OSError, ValueError) as error:
            dispatch({"type": "SET_STATUS", "text": str(error)})
            return "break"
        dispatch({"type": "UPSERT_MAP_IMAGE", "image-item": image_item})
        return "break"
    if isinstance(content, list):
        import_image_paths(content, x, y)
        return "break"
    dispatch({"type": "SET_STATUS", "text": "The clipboard does not contain an image."})
    return "break"


def handle_global_paste(event):
    focus = event.widget.focus_get()
    if focus and focus.winfo_class() in {"Entry", "TEntry", "Text", "TCombobox"}:
        return None
    if not g["state"]["model"]:
        return None
    if g["state"]["model"]["active-presentation"] != "directory-map":
        return None
    return handle_paste_image(event)


def import_image_paths(paths, x, y):
    imported = 0
    failures = []
    for number, path in enumerate(paths):
        try:
            image_item = import_image_file(
                g["state"]["folder"],
                path,
                x + number * 24,
                y + number * 24,
            )
        except (OSError, ValueError) as error:
            failures.append(str(error))
            continue
        dispatch({"type": "UPSERT_MAP_IMAGE", "image-item": image_item})
        imported += 1
    if failures:
        dispatch(
            {
                "type": "SET_STATUS",
                "text": f"Imported {imported} image(s); {len(failures)} failed.",
            }
        )
    elif imported:
        dispatch({"type": "SET_STATUS", "text": f"Imported {imported} image(s)."})


def edit_map_text_dialog(text_item):
    """Collect annotation text and presentation choices in a modal editor."""
    result = {"value": None}
    window = tk.Toplevel(g["tk"])
    window.title("Map Text")
    window.geometry("640x470")
    window.transient(g["tk"])
    window.grab_set()
    window.configure(bg=COLORS["background"])
    window.columnconfigure(0, weight=1)
    window.rowconfigure(1, weight=1)

    tk.Label(
        window,
        text="Text to place on the directory map:",
        bg=COLORS["background"],
        fg=COLORS["text"],
    ).grid(
        row=0,
        column=0,
        sticky="w",
        padx=14,
        pady=(14, 6),
    )
    editor = tk.Text(
        window,
        wrap="word",
        height=12,
        font=("Segoe UI", 11),
        undo=True,
        bg=COLORS["panel"],
        fg=COLORS["text"],
        insertbackground=COLORS["text"],
        selectbackground="#375d78",
        relief="flat",
        padx=10,
        pady=8,
        highlightthickness=1,
        highlightbackground=COLORS["panel-2"],
        highlightcolor=COLORS["accent"],
    )
    editor.grid(row=1, column=0, sticky="nsew", padx=14)
    editor.insert("1.0", text_item["text"])

    choices = tk.Frame(window, bg=COLORS["background"], padx=14, pady=12)
    choices.grid(row=2, column=0, sticky="ew")
    choices.columnconfigure(0, weight=1)
    choices.columnconfigure(1, weight=1)
    choices.columnconfigure(2, weight=1)

    alignment = tk.StringVar(value=text_item["alignment"])
    size = tk.StringVar(value=text_item["font-size"])
    color = tk.StringVar(value=text_item["color"])
    labelled_region = tk.BooleanVar(value=text_item["labelled-region"])
    region_line_width = tk.StringVar(value=text_item["region-line-width"])

    add_radio_group(
        choices,
        0,
        "Alignment",
        alignment,
        [("Left", "left"), ("Center", "center"), ("Right", "right")],
    )
    add_radio_group(
        choices,
        1,
        "Font size",
        size,
        [("Small", "small"), ("Medium", "medium"), ("Large", "large")],
    )
    add_radio_group(
        choices,
        2,
        "Color",
        color,
        [("White", "white"), ("Green", "green"), ("Blue", "blue"), ("Red", "red")],
    )

    region_row = tk.Frame(
        window,
        bg=COLORS["background"],
        padx=14,
        pady=4,
    )
    region_row.grid(row=3, column=0, sticky="w")
    tk.Checkbutton(
        region_row,
        text="Labelled Region",
        variable=labelled_region,
        bg=COLORS["background"],
        fg=COLORS["text"],
        activebackground=COLORS["background"],
        activeforeground=COLORS["text"],
        selectcolor=COLORS["panel-2"],
    ).grid(row=0, column=0, sticky="w")
    tk.Radiobutton(
        region_row,
        text="Thin",
        value="thin",
        variable=region_line_width,
        bg=COLORS["background"],
        fg=COLORS["text"],
        activebackground=COLORS["background"],
        activeforeground=COLORS["text"],
        selectcolor=COLORS["panel-2"],
    ).grid(row=0, column=1, sticky="w", padx=(24, 4))
    tk.Radiobutton(
        region_row,
        text="Thick",
        value="thick",
        variable=region_line_width,
        bg=COLORS["background"],
        fg=COLORS["text"],
        activebackground=COLORS["background"],
        activeforeground=COLORS["text"],
        selectcolor=COLORS["panel-2"],
    ).grid(row=0, column=2, sticky="w", padx=(4, 0))

    buttons = tk.Frame(
        window,
        bg=COLORS["background"],
        padx=14,
        pady=14,
    )
    buttons.grid(row=4, column=0, sticky="e")

    def accept():
        updated = dict(text_item)
        updated["text"] = editor.get("1.0", "end-1c")
        updated["alignment"] = alignment.get()
        updated["font-size"] = size.get()
        updated["color"] = color.get()
        updated["labelled-region"] = labelled_region.get()
        updated["region-line-width"] = region_line_width.get()
        updated.setdefault("width", 320)
        updated.setdefault("height", 180)
        result["value"] = updated
        window.destroy()

    ttk.Button(
        buttons,
        text="Cancel",
        command=window.destroy,
        style="Living.TButton",
    ).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(
        buttons,
        text="Save",
        command=accept,
        style="Living.TButton",
    ).grid(row=0, column=1)

    window.bind("<Escape>", lambda _event: window.destroy())
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    editor.focus_set()
    window.wait_window()
    return result["value"]


def add_radio_group(parent, column, title, variable, choices):
    frame = tk.LabelFrame(
        parent,
        text=title,
        bg=COLORS["background"],
        fg=COLORS["text"],
        padx=8,
        pady=8,
        highlightbackground=COLORS["panel-2"],
        highlightcolor=COLORS["panel-2"],
    )
    frame.grid(row=0, column=column, sticky="nsew", padx=(0, 8))
    for row, (label, value) in enumerate(choices):
        tk.Radiobutton(
            frame,
            text=label,
            value=value,
            variable=variable,
            bg=COLORS["background"],
            fg=COLORS["text"],
            activebackground=COLORS["background"],
            activeforeground=COLORS["text"],
            selectcolor=COLORS["panel-2"],
        ).grid(row=row, column=0, sticky="w")


def find_map_text(text_id):
    for item in g["state"]["model"]["map-texts"]:
        if item["id"] == text_id:
            return dict(item)
    raise ValueError(f"Map text is no longer present: {text_id}")


def map_text_font_size(value):
    return {
        "small": 8,
        "medium": 12,
        "large": 32,
    }[value]


def map_text_color(value):
    return {
        "white": "#f4f6f8",
        "green": "#70d68a",
        "blue": "#66a9ff",
        "red": "#ff6f6f",
    }[value]


def find_map_image(image_id):
    for item in g["state"]["model"]["map-images"]:
        if item["id"] == image_id:
            return dict(item)
    raise ValueError(f"Map image is no longer present: {image_id}")


def handle_delete_key(_event=None):
    if not g["state"]["model"]:
        return
    if g["state"]["model"]["active-presentation"] != "directory-map":
        return

    image_id = g["state"]["selected-image"]
    if image_id:
        image_item = find_map_image(image_id)
        label = image_item["source-name"] or image_item["asset"]
        confirmed = messagebox.askyesno(
            "Remove image?",
            f"Remove this image from the Directory Map?\n\n{label}",
            icon="warning",
            parent=g["tk"],
        )
        if confirmed:
            dispatch({"type": "DELETE_MAP_IMAGE", "image-id": image_id})
        return

    name = g["state"]["selected-entry"]
    if not name:
        return

    entry = find_entry(name)
    if entry["kind"] != "file":
        dispatch(
            {
                "type": "SET_STATUS",
                "text": "Delete only removes files; folders are left alone.",
            }
        )
        return

    confirmed = messagebox.askyesno(
        "Delete file?",
        f"Permanently delete this file?\n\n{entry['name']}",
        icon="warning",
        parent=g["tk"],
    )
    if confirmed:
        dispatch({"type": "DELETE_FILE", "path": entry["path"]})


def handle_page_up(_event=None):
    move_selected_map_layer(1)
    return "break"


def handle_page_down(_event=None):
    move_selected_map_layer(-1)
    return "break"


def move_selected_map_layer(direction):
    key = selected_map_layer_key()
    if key:
        dispatch(
            {
                "type": "MOVE_MAP_LAYER",
                "key": key,
                "direction": direction,
            }
        )


def selected_map_layer_key():
    if g["state"]["selected-image"]:
        return f"image:{g['state']['selected-image']}"
    if g["state"]["selected-text"]:
        return f"text:{g['state']['selected-text']}"
    if g["state"]["selected-entry"]:
        return f"entry:{g['state']['selected-entry']}"
    return None


def select_map_key(key):
    kind, identity = key.split(":", 1)
    if kind == "entry":
        dispatch({"type": "SELECT_ENTRY", "entry-name": identity})
    elif kind == "text":
        dispatch({"type": "SELECT_MAP_TEXT", "text-id": identity})
    elif kind == "image":
        dispatch({"type": "SELECT_MAP_IMAGE", "image-id": identity})


def current_canvas_geometry(name):
    canvas = g["widgets"]["map"]
    rectangle = g["map-items"][name][0]
    x1, y1, x2, y2 = canvas.coords(rectangle)
    return {
        "x": int(x1),
        "y": int(y1),
        "width": int(x2 - x1),
        "height": int(y2 - y1),
    }


def current_canvas_text_geometry(text_id):
    text_item = find_map_text(text_id)
    if text_item["labelled-region"]:
        return {
            "x": text_item["x"],
            "y": text_item["y"],
            "width": text_item["width"],
            "height": text_item["height"],
        }
    return {
        "x": text_item["x"],
        "y": text_item["y"],
        "width": text_item["width"],
        "height": text_item["height"],
    }


def current_canvas_image_geometry(image_id):
    canvas = g["widgets"]["map"]
    border = g["map-image-items"][image_id][0]
    x1, y1, x2, y2 = canvas.coords(border)
    return {
        "x": int(x1),
        "y": int(y1),
        "width": int(x2 - x1),
        "height": int(y2 - y1),
    }


def position_canvas_entry(name, geometry):
    canvas = g["widgets"]["map"]
    rectangle, text, *rest = g["map-items"][name]
    x = geometry["x"]
    y = geometry["y"]
    width = geometry["width"]
    height = geometry["height"]
    canvas.coords(rectangle, x, y, x + width, y + height)
    canvas.coords(text, x + 9, y + 9)
    canvas.itemconfigure(text, width=max(40, width - 18))
    if rest:
        handle = rest[0]
        canvas.coords(
            handle,
            x + width - 12,
            y + height - 12,
            x + width,
            y + height,
        )


def position_canvas_text(text_id, geometry):
    text_item = find_map_text(text_id)
    text_item.update(geometry)
    canvas = g["widgets"]["map"]
    for item in g["map-text-items"][text_id]:
        canvas.delete(item)
        g["map-item-text-id"].pop(item, None)
        g["map-text-handles"].discard(item)
    draw_map_text(canvas, text_item)


def position_canvas_image(image_id, geometry):
    canvas = g["widgets"]["map"]
    border, picture, *rest = g["map-image-items"][image_id]
    x = geometry["x"]
    y = geometry["y"]
    width = geometry["width"]
    height = geometry["height"]
    canvas.coords(border, x, y, x + width, y + height)
    canvas.coords(picture, x, y)
    if rest:
        handle = rest[0]
        canvas.coords(
            handle,
            x + width - 14,
            y + height - 14,
            x + width,
            y + height,
        )


def handle_path_entered(_event=None):
    dispatch(
        {
            "type": "NAVIGATE",
            "path": g["widgets"]["path-var"].get().strip(),
            "remember": True,
        }
    )


def handle_back():
    dispatch({"type": "BACK"})


def handle_up():
    folder = Path(g["state"]["folder"])
    dispatch({"type": "NAVIGATE", "path": str(folder.parent), "remember": True})


def handle_refresh():
    dispatch({"type": "REFRESH"})


def handle_choose_folder():
    selected = filedialog.askdirectory(initialdir=g["state"]["folder"])
    if selected:
        dispatch({"type": "NAVIGATE", "path": selected, "remember": True})


def handle_presentation_selected(_event=None):
    if g["projecting"]:
        return
    selected = g["widgets"]["mode-var"].get()
    if selected.startswith("Auto ·"):
        mode = None
    else:
        reverse = {label: mode for mode, label in MODE_LABELS.items()}
        mode = reverse.get(selected, selected.lower().replace(" ", "-"))
    dispatch({"type": "SET_PRESENTATION", "mode": mode})


def handle_trust_changed():
    if g["projecting"]:
        return
    dispatch({"type": "SET_TRUST", "value": g["widgets"]["trust-var"].get()})


def handle_tree_double_click(_event):
    tree = g["widgets"]["tree"]
    selection = tree.selection()
    if selection:
        open_entry(g["widgets"]["tree-entries"][selection[0]])


def open_entry_by_name(name):
    open_entry(find_entry(name))


def find_entry(name):
    for entry in g["state"]["model"]["entries"]:
        if entry["name"] == name:
            return entry
    raise ValueError(f"Entry is no longer present: {name}")


def open_entry(entry):
    if entry["kind"] == "folder":
        dispatch({"type": "NAVIGATE", "path": entry["path"], "remember": True})
    else:
        open_os_path(entry["path"])


def activate_button(button):
    if button["kind"] == "navigate":
        try:
            target = resolve_navigation_target(
                g["state"]["folder"],
                button["target"],
            )
        except ValueError as error:
            dispatch({"type": "SET_STATUS", "text": str(error)})
            return
        dispatch({"type": "NAVIGATE", "path": str(target), "remember": True})
        return

    if not g["state"]["trust-code"]:
        return
    command = button["command"]
    g["work-queue"].put({"command": command, "cwd": g["state"]["folder"]})
    dispatch({"type": "SET_STATUS", "text": f"Running {button['label']}…"})


def handle_open_explorer():
    open_os_path(g["state"]["folder"])


def handle_open_shell():
    try:
        subprocess.Popen(
            ["powershell"],
            cwd=g["state"]["folder"],
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    except OSError as error:
        dispatch({"type": "SET_STATUS", "text": str(error)})


def handle_edit_buttons():
    if not g["state"]["model"]:
        return
    open_button_editor()


def open_button_editor():
    window = tk.Toplevel(g["tk"])
    window.title("Living Folder Buttons")
    window.geometry("700x440")
    window.transient(g["tk"])
    window.grab_set()
    window.columnconfigure(0, weight=1)
    window.rowconfigure(0, weight=1)

    buttons = [dict(item) for item in g["state"]["model"]["buttons"]]
    detected = [dict(item) for item in g["state"]["model"]["detected-buttons"]]
    annotations = {
        filename: dict(note)
        for filename, note in g["state"]["model"]["command-annotations"].items()
    }
    rows = []
    listbox = tk.Listbox(window, font=("Segoe UI", 10))
    listbox.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=12, pady=12)

    def refresh_list():
        rows.clear()
        listbox.delete(0, "end")
        for item in buttons:
            rows.append(("declared", item))
            detail = item.get("target", item.get("command", ""))
            listbox.insert("end", f"{item['label']}  [{item['kind']}]  {detail}")
        for item in detected:
            rows.append(("detected", item))
            listbox.insert(
                "end",
                f"{item['label']}  [detected executable]  {item['filename']}",
            )

    def add_navigation():
        target = filedialog.askdirectory(
            parent=window,
            initialdir=g["state"]["folder"],
            title="Navigation button target",
        )
        if not target:
            return
        label = simpledialog.askstring(
            "Button label",
            "Label:",
            parent=window,
            initialvalue=Path(target).name,
        )
        if label:
            buttons.append(
                {
                    "id": new_button_id(),
                    "kind": "navigate",
                    "label": label,
                    "description": "",
                    "target": target,
                }
            )
            refresh_list()

    def add_command():
        label = simpledialog.askstring("Button label", "Label:", parent=window)
        if not label:
            return
        command = simpledialog.askstring(
            "Command",
            "Command to run from this folder:",
            parent=window,
        )
        if command:
            buttons.append(
                {
                    "id": new_button_id(),
                    "kind": "command",
                    "label": label,
                    "description": "",
                    "command": command,
                }
            )
            refresh_list()

    def edit_selected():
        selection = listbox.curselection()
        if not selection:
            return
        source, item = rows[selection[0]]
        label = simpledialog.askstring(
            "Button label",
            "Label:",
            parent=window,
            initialvalue=item["label"],
        )
        if not label:
            return
        if source == "detected":
            note = annotations.get(item["filename"], {})
            if isinstance(note, str):
                note = {"label": note}
            note = dict(note)
            note["label"] = label
            note.pop("hidden", None)
            annotations[item["filename"]] = note
            item["label"] = label
            refresh_list()
            return
        key = "target" if item["kind"] == "navigate" else "command"
        value = simpledialog.askstring(
            key.title(),
            f"{key.title()}:",
            parent=window,
            initialvalue=str(item[key]),
        )
        if value is None:
            return
        item["label"] = label
        item[key] = value
        refresh_list()

    def delete_selected():
        selection = listbox.curselection()
        if not selection:
            return
        source, item = rows[selection[0]]
        if source == "detected":
            note = annotations.get(item["filename"], {})
            if isinstance(note, str):
                note = {"label": note}
            note = dict(note)
            note["hidden"] = True
            annotations[item["filename"]] = note
            detected.remove(item)
        else:
            buttons.remove(item)
        refresh_list()

    def save_and_close():
        dispatch({"type": "SAVE_BUTTONS", "buttons": buttons})
        dispatch(
            {
                "type": "SAVE_COMMAND_ANNOTATIONS",
                "annotations": annotations,
            }
        )
        window.destroy()

    controls = [
        ("＋ Navigation", add_navigation),
        ("＋ Command", add_command),
        ("Edit", edit_selected),
        ("Delete", delete_selected),
        ("Save", save_and_close),
    ]
    for column, (text, command) in enumerate(controls):
        ttk.Button(
            window,
            text=text,
            command=command,
            style="Living.TButton",
        ).grid(row=1, column=column, padx=(12 if column == 0 else 0, 8), pady=(0, 12))
    refresh_list()


def start_worker():
    worker = threading.Thread(target=worker_loop, daemon=True)
    worker.start()


def worker_loop():
    while True:
        job = g["work-queue"].get()
        if job is None:
            return
        try:
            completed = subprocess.run(
                job["command"],
                cwd=job["cwd"],
                shell=isinstance(job["command"], str),
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = completed.stdout
            if completed.stderr:
                output += ("\n" if output else "") + completed.stderr
            result = {
                "return-code": completed.returncode,
                "output": output.strip() or "(no output)",
            }
        except (OSError, subprocess.SubprocessError) as error:
            result = {"return-code": None, "output": str(error)}
        g["result-queue"].put(result)


def poll_worker_results():
    try:
        result = g["result-queue"].get_nowait()
    except queue.Empty:
        result = None
    if result:
        code = result["return-code"]
        status = "Command completed." if code == 0 else f"Command failed ({code})."
        g["widgets"]["command-output"] = result["output"]
        dispatch({"type": "SET_STATUS", "text": status})
    if not g["closing"]:
        g["tk"].after(100, poll_worker_results)


def poll_runtime_inbox():
    messages = runtime.consume_summons()
    if messages:
        requested = [
            message["requested-folder"]
            for message in messages
            if message.get("requested-folder")
        ]
        if requested:
            dispatch(
                {
                    "type": "NAVIGATE",
                    "path": requested[-1],
                    "remember": True,
                }
            )
        runtime.bring_window_to_front(g["tk"])
        if not requested:
            dispatch(
                {
                    "type": "SET_STATUS",
                    "text": "Living Folders was summoned to the foreground.",
                }
            )
    if not g["closing"]:
        g["tk"].after(1000, poll_runtime_inbox)


def show_command_output():
    messagebox.showinfo(
        "Command output",
        g["widgets"]["command-output"],
        parent=g["tk"],
    )


def project_status():
    g["widgets"]["status-var"].set(g["state"]["status"])


def restore_path_entry():
    if g["state"]["folder"]:
        g["widgets"]["path-var"].set(g["state"]["folder"])


def open_os_path(path):
    try:
        os.startfile(str(path))
    except OSError as error:
        dispatch({"type": "SET_STATUS", "text": str(error)})


def visual_colors():
    return {
        "folder": COLORS["folder"],
        "executable": COLORS["executable"],
        "text": COLORS["text-file"],
        "json": COLORS["json"],
        "image": COLORS["image"],
        "file": COLORS["file"],
    }


def auto_mode_label(mode):
    return f"Auto · {MODE_LABELS.get(mode, mode.replace('-', ' ').title())}"


def format_size(size):
    if size is None:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def new_button_id():
    import uuid

    return str(uuid.uuid4())


def close_application():
    g["closing"] = True
    g["work-queue"].put(None)
    g["tk"].destroy()
