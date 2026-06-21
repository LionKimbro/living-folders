"""Tkinter control panel and projection for Living Folders."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import (
    PRESENTATION_MODES,
    inspect_folder,
    resolve_navigation_target,
    save_buttons,
    save_map_geometry,
    save_presentation,
)
from .discrete import initial_state, reduce


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
    "interaction": None,
}


def run(path):
    """Create the two-thread Tkinter application and open the requested folder."""
    build_window()
    start_worker()
    dispatch({"type": "NAVIGATE", "path": str(path), "remember": False})
    poll_worker_results()
    g["tk"].deiconify()
    g["tk"].mainloop()


def build_window():
    root = tk.Tk()
    root.withdraw()
    root.title("Living Folders")
    root.geometry("1240x820")
    root.minsize(860, 600)
    root.option_add("*tearOff", 0)
    root.protocol("WM_DELETE_WINDOW", close_application)
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
    elif name == "WRITE_BUTTONS":
        save_buttons(effect["folder"], effect["buttons"])
        dispatch({"type": "REFRESH"})
    elif name == "WRITE_MAP_GEOMETRY":
        save_map_geometry(effect["folder"], effect["geometry"])
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


def project_everything():
    g["projecting"] = True
    model = g["state"]["model"]
    path = model["folder"]
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

    actions = tk.Frame(frame, bg=COLORS["background"], padx=12, pady=8)
    actions.grid(row=0, column=0, sticky="ew")
    g["widgets"]["actions"] = actions
    project_actions()

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
    model = g["state"]["model"]

    for number, entry in enumerate(model["entries"]):
        geometry = model["map-geometry"].get(
            entry["name"],
            default_geometry(number),
        )
        draw_map_entry(canvas, entry, geometry)


def draw_map_entry(canvas, entry, geometry):
    x = geometry["x"]
    y = geometry["y"]
    width = geometry["width"]
    height = geometry["height"]
    selected = g["state"]["selected-entry"] == entry["name"]
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
    handle = canvas.create_rectangle(
        x + width - 12,
        y + height - 12,
        x + width,
        y + height,
        fill="#111111",
        outline="",
    )
    items = [rectangle, text, handle]
    g["map-items"][entry["name"]] = items
    for item in items:
        g["map-item-entry"][item] = entry["name"]
    g["map-handles"].add(handle)


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
    items = canvas.find_overlapping(
        canvas.canvasx(event.x),
        canvas.canvasy(event.y),
        canvas.canvasx(event.x),
        canvas.canvasy(event.y),
    )
    known = [item for item in reversed(items) if item in g["map-item-entry"]]
    if not known:
        g["interaction"] = None
        return

    item = known[0]
    name = g["map-item-entry"][item]
    geometry = current_canvas_geometry(name)
    g["interaction"] = {
        "entry-name": name,
        "mode": "resize" if item in g["map-handles"] else "move",
        "start-x": canvas.canvasx(event.x),
        "start-y": canvas.canvasy(event.y),
        "origin": geometry,
        "preview": geometry.copy(),
        "changed": False,
    }


def handle_map_motion(event):
    interaction = g["interaction"]
    if not interaction:
        return
    canvas = g["widgets"]["map"]
    dx = canvas.canvasx(event.x) - interaction["start-x"]
    dy = canvas.canvasy(event.y) - interaction["start-y"]
    origin = interaction["origin"]

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
    items = canvas.find_overlapping(
        canvas.canvasx(event.x),
        canvas.canvasy(event.y),
        canvas.canvasx(event.x),
        canvas.canvasy(event.y),
    )
    for item in reversed(items):
        if item in g["map-item-entry"]:
            open_entry_by_name(g["map-item-entry"][item])
            return


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


def position_canvas_entry(name, geometry):
    canvas = g["widgets"]["map"]
    rectangle, text, handle = g["map-items"][name]
    x = geometry["x"]
    y = geometry["y"]
    width = geometry["width"]
    height = geometry["height"]
    canvas.coords(rectangle, x, y, x + width, y + height)
    canvas.coords(text, x + 9, y + 9)
    canvas.itemconfigure(text, width=max(40, width - 18))
    canvas.coords(
        handle,
        x + width - 12,
        y + height - 12,
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
    for entry in g["state"]["model"]["entries"]:
        if entry["name"] == name:
            open_entry(entry)
            return


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
    listbox = tk.Listbox(window, font=("Segoe UI", 10))
    listbox.grid(row=0, column=0, columnspan=5, sticky="nsew", padx=12, pady=12)

    def refresh_list():
        listbox.delete(0, "end")
        for item in buttons:
            detail = item.get("target", item.get("command", ""))
            listbox.insert("end", f"{item['label']}  [{item['kind']}]  {detail}")

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
        item = buttons[selection[0]]
        label = simpledialog.askstring(
            "Button label",
            "Label:",
            parent=window,
            initialvalue=item["label"],
        )
        if not label:
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
        if selection:
            del buttons[selection[0]]
            refresh_list()

    def save_and_close():
        dispatch({"type": "SAVE_BUTTONS", "buttons": buttons})
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
