"""lionscliapp entrance to Living Folders."""

import json
import os
from pathlib import Path

import lionscliapp as app

from . import __version__
from .core import inspect_folder, write_manifest_template
from .runtime import (
    CLI_PROJECT_DIR_NAME,
    LAUNCHER_DIR_KEY,
    MACHINE_ROOT_KEY,
    install_launcher,
    resolve_runtime_home,
)


def main():
    invocation_folder = Path.cwd().resolve()
    runtime_home = resolve_runtime_home(create=True)
    os.chdir(runtime_home)

    app.reset()
    app.declare_app("living-folders", __version__)
    app.describe_app("Let ordinary directories present themselves as useful places.")
    app.describe_app(
        "Machine Root setup:\n"
        f'  Required key: "{MACHINE_ROOT_KEY}"\n'
        "  Value: a machine-local runtime directory, conventionally "
        "C:\\lion\\installed\\living-folders\n"
        f"  The directory owns {CLI_PROJECT_DIR_NAME}/lock.json and inbox/.\n"
        f'  Required launcher key: "{LAUNCHER_DIR_KEY}"\n'
        "  Value: a directory on PATH where living-folders.pyw is installed.\n"
        "  Launcher usage: living-folders.pyw [folder]\n"
        "lionscliapp configuration is isolated beneath that runtime directory; "
        "single-instance identity does not depend on the lionscliapp project folder.",
        "l",
    )
    app.declare_projectdir(CLI_PROJECT_DIR_NAME)
    app.set_flag("uses_locking", True)
    app.declare_key("execpath.folder", str(invocation_folder))
    app.describe_key("execpath.folder", "Folder to open, inspect, or initialize.")

    app.declare_cmd("", cmd_open)
    app.declare_cmd("open", cmd_open)
    app.declare_cmd("inspect", cmd_inspect)
    app.declare_cmd("init", cmd_init)
    app.declare_cmd("install-launcher", cmd_install_launcher)
    app.describe_cmd("", "Open the Living Folders control panel.")
    app.describe_cmd("open", "Open the Living Folders control panel.")
    app.describe_cmd("inspect", "Print the normalized folder model as JSON.")
    app.describe_cmd("init", "Create a starter .living-folder/description.json.")
    app.describe_cmd(
        "install-launcher",
        f'Install living-folders.pyw into Machine Root "{LAUNCHER_DIR_KEY}".',
    )
    app.main()


def cmd_open():
    from .app import run

    run(app.ctx["execpath.folder"])


def cmd_inspect():
    print(json.dumps(inspect_folder(app.ctx["execpath.folder"]), indent=2))


def cmd_init():
    print(write_manifest_template(app.ctx["execpath.folder"]))


def cmd_install_launcher():
    print(install_launcher())


if __name__ == "__main__":
    main()
