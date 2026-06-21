"""lionscliapp entrance to Living Folders."""

import json

import lionscliapp as app

from . import __version__
from .core import inspect_folder, write_manifest_template


def main():
    app.reset()
    app.declare_app("living-folders", __version__)
    app.describe_app("Let ordinary directories present themselves as useful places.")
    app.declare_projectdir(".living-folders")
    app.declare_key("execpath.folder", ".")
    app.describe_key("execpath.folder", "Folder to open, inspect, or initialize.")

    app.declare_cmd("", cmd_open)
    app.declare_cmd("open", cmd_open)
    app.declare_cmd("inspect", cmd_inspect)
    app.declare_cmd("init", cmd_init)
    app.describe_cmd("", "Open the Living Folders control panel.")
    app.describe_cmd("open", "Open the Living Folders control panel.")
    app.describe_cmd("inspect", "Print the normalized folder model as JSON.")
    app.describe_cmd("init", "Create a starter .living-folder.json.")
    app.main()


def cmd_open():
    from .app import run

    run(app.ctx["execpath.folder"])


def cmd_inspect():
    print(json.dumps(inspect_folder(app.ctx["execpath.folder"]), indent=2))


def cmd_init():
    print(write_manifest_template(app.ctx["execpath.folder"]))


if __name__ == "__main__":
    main()
