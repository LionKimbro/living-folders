"""lionscliapp entrance to Living Folders."""

import json
from pathlib import Path

import lionscliapp as app

from . import __version__
from .core import inspect_folder, write_manifest_template


CLI_PROJECT_DIR_NAME = ".living-folders-cli"


def main():
    invocation_folder = Path.cwd().resolve()

    app.reset()
    app.declare_app("living-folders", __version__)
    app.describe_app("Let ordinary directories present themselves as useful places.")
    app.describe_app(
        "Launch Living Folders with a stable --execroot so lionscliapp's Tk "
        "single-instance runtime owns instance.json, inbox/, and summon "
        "behavior. Use --execpath.open-at to choose the initial folder.",
        "l",
    )
    app.declare_projectdir(CLI_PROJECT_DIR_NAME)
    app.set_flag("uses_tkinter", True)
    app.declare_key("execpath.open-at", str(invocation_folder))
    app.describe_key("execpath.open-at", "Folder to open at startup, inspect, or initialize.")

    app.declare_cmd("", cmd_open)
    app.declare_cmd("open", cmd_open)
    app.declare_cmd("inspect", cmd_inspect)
    app.declare_cmd("init", cmd_init)
    app.describe_cmd("", "Open the Living Folders control panel.")
    app.describe_cmd("open", "Open the Living Folders control panel.")
    app.describe_cmd("inspect", "Print the normalized folder model as JSON.")
    app.describe_cmd("init", "Create a starter .living-folder/description.json.")
    app.set_cmd_flag("", "tkinter", True)
    app.set_cmd_flag("", "single_instance", True)
    app.set_cmd_flag("open", "tkinter", True)
    app.set_cmd_flag("open", "single_instance", True)
    app.main()


def cmd_open():
    from .app import run

    run(app.ctx["execpath.open-at"])


def cmd_inspect():
    print(json.dumps(inspect_folder(app.ctx["execpath.open-at"]), indent=2))


def cmd_init():
    print(write_manifest_template(app.ctx["execpath.open-at"]))


if __name__ == "__main__":
    main()
