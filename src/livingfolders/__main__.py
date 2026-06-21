"""Command-line entrance to Living Folders."""

import argparse
import json
import sys
from pathlib import Path

from .core import inspect_folder, write_manifest_template


def main():
    parser = argparse.ArgumentParser(
        prog="living-folders",
        description="Let a directory present itself according to its purpose.",
    )
    parser.add_argument("folder", nargs="?", default=".")
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="print the folder portrait as JSON instead of opening the GUI",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="write a starter .living-folder.json into the folder",
    )
    arguments = parser.parse_args()

    try:
        if arguments.init:
            path = write_manifest_template(arguments.folder)
            print(path)
            return

        if arguments.inspect:
            portrait = inspect_folder(arguments.folder)
            print(json.dumps(portrait, indent=2, ensure_ascii=False))
            return

        from .app import run

        run(Path(arguments.folder))
    except ValueError as error:
        parser.exit(2, f"living-folders: {error}\n")


if __name__ == "__main__":
    main()
