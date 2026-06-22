import json
import sys
import tempfile
import unittest
from pathlib import Path

from livingfolders.core import (
    delete_immediate_file,
    inspect_folder,
    save_code_trust,
    save_command_annotations,
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

    def test_detected_button_can_be_relabelled_or_tombstoned(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "build.bat").write_text("@echo off\n", encoding="utf-8")

            save_command_annotations(
                folder,
                {
                    "build.bat": {
                        "label": "Build Everything",
                        "description": "",
                        "hidden": False,
                    }
                },
            )
            model = inspect_folder(folder)
            self.assertEqual("Build Everything", model["detected-buttons"][0]["label"])

            save_command_annotations(
                folder,
                {
                    "build.bat": {
                        "label": "Build Everything",
                        "description": "",
                        "hidden": True,
                    }
                },
            )
            model = inspect_folder(folder)
            self.assertEqual([], model["detected-buttons"])
            self.assertTrue(model["command-annotations"]["build.bat"]["hidden"])

    def test_delete_only_allows_immediate_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            file_path = folder / "goodbye.txt"
            file_path.write_text("bye", encoding="utf-8")
            nested = folder / "nested"
            nested.mkdir()
            nested_file = nested / "not-from-here.txt"
            nested_file.write_text("stay", encoding="utf-8")

            delete_immediate_file(folder, file_path)

            self.assertFalse(file_path.exists())
            with self.assertRaises(ValueError):
                delete_immediate_file(folder, nested_file)
            self.assertTrue(nested_file.exists())

    def test_code_trust_is_stored_by_the_particular_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trusted = root / "trusted"
            untrusted = root / "untrusted"
            trusted.mkdir()
            untrusted.mkdir()

            save_code_trust(trusted, True)

            self.assertTrue(inspect_folder(trusted)["trust-runnable-code"])
            self.assertFalse(inspect_folder(untrusted)["trust-runnable-code"])


if __name__ == "__main__":
    unittest.main()
