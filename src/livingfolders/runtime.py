"""Single-instance runtime and FileTalk summons channel on lionscliapp lock.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import machineroot


MACHINE_ROOT_KEY = "living-folders-runtime"
LAUNCHER_DIR_KEY = "path-dir"
WINDOW_TOKEN = "LIVING_FOLDERS_MAIN_WINDOW_99A72E"
CLI_PROJECT_DIR_NAME = ".living-folders-cli"
LOCK_NAME = "lock.json"
LAUNCHER_NAME = "living-folders.pyw"

SW_RESTORE = 9


def resolve_runtime_home(create=False):
    """Resolve the machine-local runtime home through Machine Root."""
    try:
        value = machineroot.get(MACHINE_ROOT_KEY)
    except machineroot.MachineRootError as error:
        raise RuntimeError(
            f'Machine Root key "{MACHINE_ROOT_KEY}" is required. '
            "Define it as the directory that should hold "
            f"{CLI_PROJECT_DIR_NAME}/{LOCK_NAME} and inbox/."
        ) from error

    home = Path(value).expanduser().resolve()
    if create:
        home.mkdir(parents=True, exist_ok=True)
        (home / "inbox").mkdir(parents=True, exist_ok=True)
    return home


def resolve_cli_project_dir(create=False):
    directory = resolve_runtime_home(create=create) / CLI_PROJECT_DIR_NAME
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_lock_path(create=False):
    return resolve_cli_project_dir(create=create) / LOCK_NAME


def resolve_launcher_dir(create=False):
    """Resolve the shared executable-script directory through Machine Root."""
    try:
        value = machineroot.get(LAUNCHER_DIR_KEY)
    except machineroot.MachineRootError as error:
        raise RuntimeError(
            f'Machine Root key "{LAUNCHER_DIR_KEY}" is required to install '
            f"{LAUNCHER_NAME}. Define it as a directory present on PATH."
        ) from error
    directory = Path(value).expanduser().resolve()
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def install_launcher():
    """Atomically install the tiny pythonw launcher into path-dir."""
    target = resolve_launcher_dir(create=True) / LAUNCHER_NAME
    source = (
        '"""Summon the single Living Folders window, or launch it when absent."""\n'
        "\n"
        "from livingfolders.runtime import launcher_main\n"
        "\n"
        "\n"
        "launcher_main()\n"
    )
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(source)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return target


def acquire_instance():
    """Acquire lionscliapp-style lock.json and attach Living Folders metadata."""
    path = resolve_lock_path(create=True)
    instance = {
        "lock_id": str(uuid.uuid4()),
        "command": "open",
        "pid": os.getpid(),
        "created_at": now_iso(),
        "window-handle": None,
        "current-folder": None,
    }
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(instance, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        return None

    instance["lock-path"] = str(path)
    return instance


def publish_window_handle(instance, hwnd):
    instance["window-handle"] = int(hwnd)
    write_lock(instance)


def publish_current_folder(instance, folder):
    instance["current-folder"] = str(Path(folder).resolve())
    write_lock(instance)


def release_instance(instance):
    """Remove only this execution's framework-style lock record."""
    if not instance:
        return
    path = Path(instance["lock-path"])
    current = read_json_object(path)
    if current.get("lock_id") == instance["lock_id"]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def write_lock(instance):
    data = {
        "lock_id": instance["lock_id"],
        "command": instance["command"],
        "pid": instance["pid"],
        "created_at": instance["created_at"],
        "window-handle": instance["window-handle"],
        "current-folder": instance["current-folder"],
    }
    atomic_write_json(Path(instance["lock-path"]), data)


def read_lock():
    return read_json_object(resolve_lock_path(create=True))


def instance_appears_alive():
    lock = read_lock()
    pid = lock.get("pid")
    return (
        isinstance(pid, int)
        and is_process_alive(pid)
    )


def send_summons(requested_folder=None):
    """Atomically place a one-shot foreground request into the runtime inbox."""
    home = resolve_runtime_home(create=True)
    message = {
        "living-folders-message": "1",
        "id": str(uuid.uuid4()),
        "type": "summon",
        "created": now_iso(),
        "sender-pid": os.getpid(),
        "requested-folder": str(Path(requested_folder).resolve())
        if requested_folder
        else None,
    }
    target = home / "inbox" / f"summon-{message['id']}.json"
    atomic_write_json(target, message)
    return target


def consume_summons():
    """Read complete summons messages, delete them, and return canonical records."""
    inbox = resolve_runtime_home(create=True) / "inbox"
    messages = []
    for path in sorted(inbox.glob("*.json"), key=lambda item: item.name):
        data = read_json_object(path)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        if data.get("type") == "summon":
            messages.append(data)
    return messages


def bring_window_to_front(root):
    """Best-effort restore and foreground on Windows."""
    root.deiconify()
    try:
        root.state("normal")
    except Exception:
        pass
    root.lift()
    root.attributes("-topmost", True)
    root.update_idletasks()

    bring_hwnd_to_front(int(root.winfo_id()))
    root.focus_force()
    root.after(180, lambda: root.attributes("-topmost", False))


def bring_hwnd_to_front(hwnd):
    """Foreground a known window handle from the user-invoked launcher."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
    user32.SetForegroundWindow(wintypes.HWND(hwnd))


def launch_or_summon(requested_folder=None):
    """Launcher behavior: summon a live instance, otherwise start one."""
    requested_folder = Path(requested_folder or Path.cwd()).resolve()
    if instance_appears_alive():
        lock = read_lock()
        hwnd = lock.get("window-handle")
        if isinstance(hwnd, int) and hwnd > 0:
            bring_hwnd_to_front(hwnd)
        send_summons(requested_folder)
        return "summoned"

    remove_stale_lock()
    command = [
        sys.executable,
        "-m",
        "livingfolders",
        "--execpath.folder",
        str(requested_folder),
    ]
    subprocess.Popen(
        command,
        cwd=requested_folder,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    return "launched"


def launcher_main(argv=None):
    """Accept an optional folder argument and launch or redirect accordingly."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) > 1:
        raise SystemExit("usage: living-folders.pyw [folder]")
    requested_folder = arguments[0] if arguments else Path.cwd()
    launch_or_summon(requested_folder)


def remove_stale_lock():
    path = resolve_lock_path(create=True)
    lock = read_json_object(path)
    pid = lock.get("pid")
    if not isinstance(pid, int) or not is_process_alive(pid):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def is_process_alive(pid):
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    if pid <= 0:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True


def read_json_object(path):
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def atomic_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def now_iso():
    return datetime.now(timezone.utc).isoformat()
