"""Machine-wide single-instance runtime and FileTalk summons channel."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import uuid
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

import machineroot


MACHINE_ROOT_KEY = "living-folders-runtime"
LAUNCHER_DIR_KEY = "path-dir"
MUTEX_NAME = "Local\\LionKimbro_LivingFolders_SingleInstance_v1"
WINDOW_TOKEN = "LIVING_FOLDERS_MAIN_WINDOW_99A72E"
LOCK_NAME = "lock-file.json"
LAUNCHER_NAME = "living-folders.pyw"

ERROR_ALREADY_EXISTS = 183
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
SW_RESTORE = 9


def resolve_runtime_home(create=False):
    """Resolve the machine-local runtime home through Machine Root."""
    try:
        value = machineroot.get(MACHINE_ROOT_KEY)
    except machineroot.MachineRootError as error:
        raise RuntimeError(
            f'Machine Root key "{MACHINE_ROOT_KEY}" is required. '
            "Define it as the directory that should hold lock-file.json and inbox/."
        ) from error

    home = Path(value).expanduser().resolve()
    if create:
        home.mkdir(parents=True, exist_ok=True)
        (home / "inbox").mkdir(parents=True, exist_ok=True)
    return home


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
    """Acquire the hard Windows mutex and publish a human-readable lock record."""
    home = resolve_runtime_home(create=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None

    instance = {
        "id": str(uuid.uuid4()),
        "pid": os.getpid(),
        "started": now_iso(),
        "runtime-home": str(home),
        "mutex-handle": handle,
        "window-handle": None,
        "current-folder": None,
    }
    write_lock(instance)
    return instance


def publish_window_handle(instance, hwnd):
    instance["window-handle"] = int(hwnd)
    write_lock(instance)


def publish_current_folder(instance, folder):
    instance["current-folder"] = str(Path(folder).resolve())
    write_lock(instance)


def release_instance(instance):
    """Remove only this instance's lock record and release its mutex handle."""
    if not instance:
        return
    home = Path(instance["runtime-home"])
    path = home / LOCK_NAME
    current = read_json_object(path)
    if current.get("id") == instance["id"]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(instance["mutex-handle"])


def write_lock(instance):
    data = {
        "living-folders-lock": "1",
        "id": instance["id"],
        "pid": instance["pid"],
        "started": instance["started"],
        "window-handle": instance["window-handle"],
        "current-folder": instance["current-folder"],
        "mutex-name": MUTEX_NAME,
    }
    atomic_write_json(Path(instance["runtime-home"]) / LOCK_NAME, data)


def read_lock():
    return read_json_object(resolve_runtime_home(create=True) / LOCK_NAME)


def instance_appears_alive():
    lock = read_lock()
    pid = lock.get("pid")
    return (
        isinstance(pid, int)
        and is_process_alive(pid)
        and named_mutex_exists()
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
    path = resolve_runtime_home(create=True) / LOCK_NAME
    lock = read_json_object(path)
    pid = lock.get("pid")
    if not isinstance(pid, int) or not is_process_alive(pid):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def is_process_alive(pid):
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


def named_mutex_exists():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
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
