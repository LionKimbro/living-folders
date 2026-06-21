import json
import sys
import tempfile
import unittest
from pathlib import Path

from livingfolders.core import (
    inspect_folder,
    save_map_geometry,
    save_presentation,
    write_manifest_template,
)


class FolderModelTests(unittest.TestCase):
    def test_project_root_is_inferred_and_python_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / ".git").mkdir()
            (folder / "run.py").write_text("print('hello')\n", encoding="utf-8")

            model = inspect_folder(folder)

            self.assertEqual("project-root", model["inferred-presentation"])
            self.assertEqual("project-root", model["active-presentation"])
            self.assertIsNone(model["explicit-presentation"])
            self.assertEqual([sys.executable, str(folder / "run.py")], model["detected-buttons"][0]["command"])

    def test_explicit_presentation_overrides_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / ".git").mkdir()
            (folder / ".living-folder.json").write_text(
                json.dumps({"presentation-mode": "directory-map"}),
                encoding="utf-8",
            )

            model = inspect_folder(folder)

            self.assertEqual("project-root", model["inferred-presentation"])
            self.assertEqual("directory-map", model["active-presentation"])
            self.assertEqual("directory-map", model["explicit-presentation"])

    def test_navigation_and_command_buttons_are_normalized(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            manifest = {
                "buttons": [
                    {"kind": "navigate", "label": "Elsewhere", "target": ".."},
                    {"kind": "command", "label": "Status", "command": "git status"},
                ]
            }
            (folder / ".living-folder.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )

            buttons = inspect_folder(folder)["buttons"]

            self.assertEqual("navigate", buttons[0]["kind"])
            self.assertEqual("..", buttons[0]["target"])
            self.assertEqual("command", buttons[1]["kind"])
            self.assertEqual("git status", buttons[1]["command"])

    def test_writes_are_atomic_and_preserve_unknown_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path = write_manifest_template(folder)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["future-field"] = {"still": "here"}
            path.write_text(json.dumps(data), encoding="utf-8")

            save_presentation(folder, "directory-map")
            save_map_geometry(
                folder,
                {"alpha.txt": {"x": 10, "y": 20, "width": 100, "height": 60}},
            )
            saved = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual("0.2", saved["living-folder"])
            self.assertEqual({"still": "here"}, saved["future-field"])
            self.assertEqual("directory-map", saved["presentation-mode"])
            self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
