import json
import sys
import tempfile
import unittest
from pathlib import Path

from livingfolders.core import inspect_folder, write_manifest_template


class FolderPortraitTests(unittest.TestCase):
    def test_project_root_is_inferred_and_python_is_runnable(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / ".git").mkdir()
            (folder / "README.md").write_text("# hello\n", encoding="utf-8")
            (folder / "run.py").write_text("print('hello')\n", encoding="utf-8")

            portrait = inspect_folder(folder)

            self.assertEqual("project-root", portrait["manifest"]["role"])
            self.assertTrue(portrait["signals"]["is-git-repository"])
            self.assertTrue(portrait["signals"]["has-readme"])
            self.assertEqual(1, len(portrait["commands"]))
            self.assertEqual(
                [sys.executable, str(folder / "run.py")],
                portrait["commands"][0]["command"],
            )

    def test_manifest_is_normalized_into_one_interior_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "launch").mkdir()
            (folder / "go.cmd").write_text("@echo off\n", encoding="utf-8")
            manifest = {
                "title": "Print Queue",
                "role": "factory",
                "places": {"launch": "Waiting Jobs"},
                "commands": {"go.cmd": "Run Queue"},
                "actions": [{"label": "Status", "command": ["git", "status"]}],
            }
            (folder / ".living-folder.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            portrait = inspect_folder(folder)

            self.assertEqual("factory", portrait["manifest"]["role"])
            self.assertEqual(
                "Waiting Jobs",
                portrait["manifest"]["places"]["launch"]["label"],
            )
            self.assertEqual("Run Queue", portrait["commands"][0]["label"])
            self.assertEqual("Status", portrait["commands"][1]["label"])

    def test_init_writes_an_atomic_editable_constitution(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)

            path = write_manifest_template(folder)
            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(".living-folder.json", path.name)
            self.assertEqual("0.1", data["living-folder"])
            self.assertIn("purpose", data)
            self.assertFalse(path.with_suffix(path.suffix + ".tmp").exists())

            with self.assertRaises(ValueError):
                write_manifest_template(folder)


if __name__ == "__main__":
    unittest.main()
