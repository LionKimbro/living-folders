"""Tkinter presentation for a Living Folder portrait."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import inspect_folder, write_manifest_template


g = {
    "tk": None,
    "widgets": {},
    "portrait": None,
    "folder": None,
    "work-queue": queue.Queue(),
    "result-queue": queue.Queue(),
    "worker": None,
    "closing": False,
}


ROLE_STYLE = {
    "cockpit": ("#172033", "#62d9ff", "COMMAND DECK"),
    "factory": ("#2b2118", "#ffb454", "PRODUCTION FLOOR"),
    "gallery": ("#251d31", "#e3a8ff", "GALLERY"),
    "hallway": ("#20252a", "#b8c6cf", "PASSAGE"),
    "inbox": ("#182832", "#72d7c6", "ARRIVALS"),
    "library": ("#25221b", "#d9c27c", "READING ROOM"),
    "project-root": ("#17251d", "#79dd91", "PROJECT GROUND"),
    "ruin": ("#28251f", "#c1a77a", "OLD GROUND"),
    "staging-area": ("#27221a", "#e6bd66", "STAGING"),
    "vault": ("#201c29", "#bba5ef", "VAULT"),
    "warehouse": ("#232629", "#c0c7ce", "STORAGE"),
    "workbench": ("#20251f", "#a6d189", "WORKBENCH"),
}


def run(path):
    """Build the window, start the sole worker, and enter Tk's event loop."""
    g["folder"] = Path(path).expanduser().resolve()
    g["tk"] = tk.Tk()
    g["tk"].title("Living Folders")
    g["tk"].geometry("1120x760")
    g["tk"].minsize(760, 560)
    g["tk"].protocol("WM_DELETE_WINDOW", close_application)

    build_styles()
    build_shell()
    start_worker()
    open_folder(g["folder"])
    poll_worker_results()
    g["tk"].mainloop()


def build_styles():
    style = ttk.Style(g["tk"])
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(".", font=("Segoe UI", 10))
    style.configure("Living.TFrame", background="#151719")
    style.configure(
        "Living.TButton",
        padding=(12, 8),
        background="#30363d",
        foreground="#f0f3f6",
        borderwidth=0,
    )
    style.map("Living.TButton", background=[("active", "#414952")])
    style.configure(
        "Primary.TButton",
        padding=(14, 9),
        background="#39734c",
        foreground="#ffffff",
        borderwidth=0,
    )
    style.map("Primary.TButton", background=[("active", "#4b9162")])
    style.configure(
        "Quiet.TButton",
        padding=(9, 6),
        background="#22272b",
        foreground="#c7d0d9",
        borderwidth=0,
    )
    style.map("Quiet.TButton", background=[("active", "#343b42")])
    style.configure(
        "Living.TCheckbutton",
        background="#151719",
        foreground="#d8dee4",
        indicatorcolor="#2b3035",
    )
    style.map(
        "Living.TCheckbutton",
        background=[("active", "#151719")],
        indicatorcolor=[("selected", "#58a66e")],
    )


def build_shell():
    root = g["tk"]
    root.configure(background="#151719")

    toolbar = ttk.Frame(root, style="Living.TFrame", padding=(16, 12))
    toolbar.grid(row=0, column=0, sticky="ew")
    toolbar.columnconfigure(1, weight=1)

    ttk.Button(
        toolbar,
        text="Choose folder",
        command=choose_folder,
        style="Quiet.TButton",
    ).grid(row=0, column=0, padx=(0, 10))

    path_label = tk.Label(
        toolbar,
        text="",
        anchor="w",
        bg="#151719",
        fg="#89939d",
        font=("Cascadia Mono", 9),
    )
    path_label.grid(row=0, column=1, sticky="ew")

    ttk.Button(
        toolbar,
        text="Refresh",
        command=refresh,
        style="Quiet.TButton",
    ).grid(row=0, column=2, padx=(10, 0))

    body = tk.Canvas(root, bg="#151719", highlightthickness=0)
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=body.yview)
    body.configure(yscrollcommand=scrollbar.set)
    body.grid(row=1, column=0, sticky="nsew")
    scrollbar.grid(row=1, column=1, sticky="ns")

    content = tk.Frame(body, bg="#151719")
    content_window = body.create_window((0, 0), window=content, anchor="nw")
    content.bind(
        "<Configure>",
        lambda _event: body.configure(scrollregion=body.bbox("all")),
    )
    body.bind(
        "<Configure>",
        lambda event: body.itemconfigure(content_window, width=event.width),
    )
    body.bind_all(
        "<MouseWheel>",
        lambda event: body.yview_scroll(int(-event.delta / 120), "units"),
    )

    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)

    g["widgets"] = {
        "path-label": path_label,
        "body": body,
        "content": content,
    }


def choose_folder():
    selected = filedialog.askdirectory(initialdir=g["folder"])
    if selected:
        open_folder(Path(selected))


def open_folder(path):
    try:
        portrait = inspect_folder(path)
    except ValueError as error:
        messagebox.showerror("Living Folders", str(error))
        return

    g["folder"] = Path(portrait["folder"])
    g["portrait"] = portrait
    g["widgets"]["path-label"].configure(text=portrait["folder"])
    render_portrait()


def refresh():
    open_folder(g["folder"])


def render_portrait():
    content = g["widgets"]["content"]
    for child in content.winfo_children():
        child.destroy()

    portrait = g["portrait"]
    manifest = portrait["manifest"]
    role = manifest["role"]
    background, accent, room_name = ROLE_STYLE.get(
        role, ("#202427", "#aab4bd", role.upper())
    )
    content.configure(bg=background)
    g["widgets"]["body"].configure(bg=background)

    render_header(content, manifest, background, accent, room_name)
    render_signals(content, portrait["signals"], background, accent)
    render_warning(content, manifest, background)
    render_commands(content, portrait["commands"], background, accent)
    render_places(content, portrait["entries"], background, accent)
    render_files(content, portrait["entries"], background, accent)
    render_footer(content, portrait, background, accent)


def render_header(parent, manifest, background, accent, room_name):
    frame = tk.Frame(parent, bg=background, padx=34, pady=28)
    frame.grid(row=0, column=0, sticky="ew")
    frame.columnconfigure(0, weight=1)

    tk.Label(
        frame,
        text=f"{room_name}  /  {manifest['state'].upper()}  /  {manifest['mood'].upper()}",
        bg=background,
        fg=accent,
        font=("Segoe UI Semibold", 9),
    ).grid(row=0, column=0, sticky="w")

    tk.Label(
        frame,
        text=manifest["title"],
        bg=background,
        fg="#f4f6f8",
        font=("Segoe UI Semibold", 30),
        anchor="w",
    ).grid(row=1, column=0, sticky="ew", pady=(5, 5))

    tk.Label(
        frame,
        text=manifest["purpose"],
        bg=background,
        fg="#bdc5cc",
        font=("Segoe UI", 12),
        anchor="w",
        justify="left",
        wraplength=900,
    ).grid(row=2, column=0, sticky="ew")


def render_signals(parent, signals, background, accent):
    frame = tk.Frame(parent, bg=background, padx=34, pady=4)
    frame.grid(row=1, column=0, sticky="ew")

    values = [
        (signals["folder-count"], "places"),
        (signals["file-count"], "files"),
        (signals["recent-count"], "touched this week"),
        (signals["year-old-count"], "year-old"),
    ]

    if signals["is-git-repository"]:
        values.append(("✓", "git repository"))
    if signals["has-readme"]:
        values.append(("✓", "readme"))

    for column, (value, label) in enumerate(values):
        cell = tk.Frame(frame, bg="#000000", padx=13, pady=9)
        cell.configure(highlightbackground=accent, highlightthickness=1)
        cell.grid(row=0, column=column, padx=(0, 8), sticky="w")
        tk.Label(
            cell,
            text=str(value),
            bg="#000000",
            fg=accent,
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0)
        tk.Label(
            cell,
            text=label,
            bg="#000000",
            fg="#aab2b9",
            font=("Segoe UI", 9),
        ).grid(row=1, column=0)


def render_warning(parent, manifest, background):
    if not manifest["warning"]:
        return

    tk.Label(
        parent,
        text=f"⚠  {manifest['warning']}",
        bg="#4a3520",
        fg="#ffd89b",
        padx=18,
        pady=12,
        anchor="w",
        justify="left",
        wraplength=900,
    ).grid(row=2, column=0, sticky="ew", padx=34, pady=(18, 0))


def render_commands(parent, commands, background, accent):
    section = section_frame(parent, 3, "Local affordances", background, accent)

    trust = tk.BooleanVar(value=False)
    g["widgets"]["trust"] = trust
    ttk.Checkbutton(
        section,
        text="I trust runnable code in this folder",
        variable=trust,
        command=update_command_buttons,
        style="Living.TCheckbutton",
    ).grid(row=1, column=0, sticky="w", pady=(0, 12))

    buttons = []
    if not commands:
        quiet_label(
            section,
            "No runnable files or declared actions were found.",
            background,
        ).grid(row=2, column=0, sticky="w")
    else:
        grid = tk.Frame(section, bg=background)
        grid.grid(row=2, column=0, sticky="ew")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        for number, command in enumerate(commands):
            card = tk.Frame(
                grid,
                bg="#101315",
                padx=14,
                pady=12,
                highlightbackground="#343b40",
                highlightthickness=1,
            )
            card.grid(
                row=number // 2,
                column=number % 2,
                sticky="nsew",
                padx=(0, 10) if number % 2 == 0 else (0, 0),
                pady=(0, 10),
            )
            card.columnconfigure(0, weight=1)

            style = (
                "Primary.TButton"
                if command["importance"] == "primary"
                else "Living.TButton"
            )
            button = ttk.Button(
                card,
                text=command["label"],
                command=lambda item=command: queue_command(item),
                style=style,
                state="disabled",
            )
            button.grid(row=0, column=0, sticky="ew")
            buttons.append(button)

            if command["description"]:
                tk.Label(
                    card,
                    text=command["description"],
                    bg="#101315",
                    fg="#9ca6ae",
                    anchor="w",
                    justify="left",
                    wraplength=390,
                ).grid(row=1, column=0, sticky="ew", pady=(7, 0))

    output = tk.Text(
        section,
        height=7,
        bg="#090b0c",
        fg="#c8d1d9",
        insertbackground="#ffffff",
        font=("Cascadia Mono", 9),
        relief="flat",
        padx=12,
        pady=10,
        state="disabled",
    )
    output.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    g["widgets"]["output"] = output
    set_output("Commands run from this folder. Their output will appear here.")

    g["widgets"]["command-buttons"] = buttons


def render_places(parent, entries, background, accent):
    folders = [entry for entry in entries if entry["kind"] == "folder"]
    section = section_frame(parent, 4, "Places within this place", background, accent)

    if not folders:
        quiet_label(section, "No subfolders.", background).grid(
            row=1, column=0, sticky="w"
        )
        return

    grid = tk.Frame(section, bg=background)
    grid.grid(row=1, column=0, sticky="ew")
    for column in range(3):
        grid.columnconfigure(column, weight=1)

    for number, entry in enumerate(folders):
        role = entry["role"] or "hallway"
        _room_background, room_accent, room_name = ROLE_STYLE.get(
            role, ("#202427", "#aab4bd", role.upper())
        )
        card = tk.Frame(
            grid,
            bg="#121517",
            padx=15,
            pady=13,
            cursor="hand2",
            highlightbackground="#343b40",
            highlightthickness=1,
        )
        card.grid(
            row=number // 3,
            column=number % 3,
            sticky="nsew",
            padx=(0, 9),
            pady=(0, 9),
        )
        card.bind("<Button-1>", lambda _event, item=entry: open_folder(item["path"]))
        for child in card.winfo_children():
            child.bind("<Button-1>", lambda _event, item=entry: open_folder(item["path"]))

        tk.Label(
            card,
            text=room_name,
            bg="#121517",
            fg=room_accent,
            font=("Segoe UI Semibold", 8),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        title = tk.Label(
            card,
            text=entry["label"],
            bg="#121517",
            fg="#eff2f4",
            font=("Segoe UI Semibold", 12),
            anchor="w",
        )
        title.grid(row=1, column=0, sticky="ew", pady=(2, 2))
        title.bind("<Button-1>", lambda _event, item=entry: open_folder(item["path"]))

        note = entry["description"] or age_phrase(entry["age-days"])
        tk.Label(
            card,
            text=note,
            bg="#121517",
            fg="#929ca4",
            anchor="w",
            justify="left",
            wraplength=260,
        ).grid(row=2, column=0, sticky="ew")


def render_files(parent, entries, background, accent):
    files = [entry for entry in entries if entry["kind"] == "file"]
    section = section_frame(parent, 5, "Material", background, accent)

    if not files:
        quiet_label(section, "No files.", background).grid(row=1, column=0, sticky="w")
        return

    for number, entry in enumerate(files[:40], 1):
        row = tk.Frame(section, bg=background, pady=4)
        row.grid(row=number, column=0, sticky="ew")
        row.columnconfigure(0, weight=1)

        label = tk.Label(
            row,
            text=entry["name"],
            bg=background,
            fg="#dbe1e6",
            anchor="w",
            cursor="hand2",
        )
        label.grid(row=0, column=0, sticky="ew")
        label.bind("<Double-Button-1>", lambda _event, item=entry: open_path(item["path"]))

        tk.Label(
            row,
            text=f"{format_size(entry['size'])}  ·  {age_phrase(entry['age-days'])}",
            bg=background,
            fg="#7f8991",
            anchor="e",
        ).grid(row=0, column=1, sticky="e")

    if len(files) > 40:
        quiet_label(
            section,
            f"{len(files) - 40} more files remain in the raw directory.",
            background,
        ).grid(row=41, column=0, sticky="w", pady=(7, 0))


def render_footer(parent, portrait, background, accent):
    frame = tk.Frame(parent, bg=background, padx=34, pady=8)
    frame.grid(row=6, column=0, sticky="ew", pady=(0, 26))

    ttk.Button(
        frame,
        text="Open in Explorer",
        command=lambda: open_path(portrait["folder"]),
        style="Quiet.TButton",
    ).grid(row=0, column=0, padx=(0, 8))

    if portrait["manifest-path"]:
        ttk.Button(
            frame,
            text="Edit constitution",
            command=lambda: open_path(portrait["manifest-path"]),
            style="Quiet.TButton",
        ).grid(row=0, column=1)
    else:
        ttk.Button(
            frame,
            text="Give this folder a constitution",
            command=create_manifest,
            style="Quiet.TButton",
        ).grid(row=0, column=1)

    tk.Label(
        frame,
        text="The folder is the application. Living Folders is only the lens.",
        bg=background,
        fg=accent,
        font=("Segoe UI", 9, "italic"),
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(18, 0))


def section_frame(parent, row, title, background, accent):
    section = tk.Frame(parent, bg=background, padx=34, pady=20)
    section.grid(row=row, column=0, sticky="ew")
    section.columnconfigure(0, weight=1)
    tk.Label(
        section,
        text=title.upper(),
        bg=background,
        fg=accent,
        font=("Segoe UI Semibold", 9),
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", pady=(0, 12))
    return section


def quiet_label(parent, text, background):
    return tk.Label(parent, text=text, bg=background, fg="#858f97", anchor="w")


def update_command_buttons():
    state = "normal" if g["widgets"]["trust"].get() else "disabled"
    for button in g["widgets"]["command-buttons"]:
        button.configure(state=state)


def queue_command(command):
    if not g["widgets"]["trust"].get():
        return

    set_output(f"$ {display_command(command['command'])}\n\nRunning…")
    for button in g["widgets"]["command-buttons"]:
        button.configure(state="disabled")
    g["work-queue"].put(
        {
            "command": command["command"],
            "cwd": g["portrait"]["folder"],
        }
    )


def start_worker():
    worker = threading.Thread(
        target=worker_loop,
        name="living-folders-worker",
        daemon=True,
    )
    worker.start()
    g["worker"] = worker


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
                text=True,
                capture_output=True,
                timeout=300,
            )
            output = completed.stdout
            if completed.stderr:
                output += ("\n" if output else "") + completed.stderr
            result = {
                "ok": completed.returncode == 0,
                "return-code": completed.returncode,
                "output": output.strip() or "(no output)",
            }
        except (OSError, subprocess.SubprocessError) as error:
            result = {
                "ok": False,
                "return-code": None,
                "output": str(error),
            }

        g["result-queue"].put(result)


def poll_worker_results():
    try:
        result = g["result-queue"].get_nowait()
    except queue.Empty:
        result = None

    if result:
        status = "completed" if result["ok"] else "failed"
        code = (
            f" (exit {result['return-code']})"
            if result["return-code"] is not None
            else ""
        )
        set_output(f"{status}{code}\n\n{result['output']}")
        update_command_buttons()

    if not g["closing"]:
        g["tk"].after(100, poll_worker_results)


def set_output(text):
    output = g["widgets"].get("output")
    if not output:
        return
    output.configure(state="normal")
    output.delete("1.0", "end")
    output.insert("1.0", text)
    output.configure(state="disabled")


def create_manifest():
    try:
        path = write_manifest_template(g["folder"])
    except ValueError as error:
        messagebox.showerror("Living Folders", str(error))
        return

    open_path(path)
    refresh()


def open_path(path):
    path = str(path)
    try:
        os.startfile(path)
    except OSError as error:
        messagebox.showerror("Living Folders", str(error))


def display_command(command):
    if isinstance(command, str):
        return command
    return subprocess.list2cmdline(command)


def format_size(size):
    if size is None:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def age_phrase(days):
    if days == 0:
        return "touched today"
    if days == 1:
        return "touched yesterday"
    if days < 30:
        return f"touched {days} days ago"
    if days < 365:
        return f"quiet for {days // 30} months"
    return f"quiet for {days // 365} years"


def close_application():
    g["closing"] = True
    g["work-queue"].put(None)
    g["tk"].destroy()
