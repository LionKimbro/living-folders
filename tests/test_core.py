import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from livingfolders.core import (
    extract_iso_days,
    delete_immediate_file,
    get_cached_image_path,
    import_clipboard_image,
    import_image_file,
    inspect_folder,
    save_code_trust,
    save_command_annotations,
    save_map_geometry,
    save_map_entry_states,
    save_map_images,
    save_map_z_order,
    save_map_texts,
    save_presentation,
    write_manifest_template,
)


class FolderModelTests(unittest.TestCase):
    def description_path(self, folder):
        return folder / ".living-folder" / "description.json"

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

            self.assertEqual("0.3", saved["living-folder"])
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

    def test_directory_map_texts_are_normalized_and_persisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            texts = [
                {
                    "id": "note-1",
                    "text": "This is the north wall.",
                    "x": 120,
                    "y": 80,
                    "alignment": "center",
                    "font-size": "large",
                    "color": "green",
                    "labelled-region": False,
                    "region-line-width": "thick",
                    "width": 320,
                    "height": 180,
                }
            ]

            save_map_texts(folder, texts)
            model = inspect_folder(folder)

            self.assertEqual(texts, model["map-texts"])
            raw = json.loads(self.description_path(folder).read_text(encoding="utf-8"))
            self.assertEqual(texts, raw["directory-map"]["texts"])

    def test_legacy_manifest_is_read_but_next_write_uses_directory_form(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            legacy = folder / ".living-folder.json"
            legacy.write_text(
                json.dumps({"title": "Legacy Place", "future": {"kept": True}}),
                encoding="utf-8",
            )

            self.assertEqual("Legacy Place", inspect_folder(folder)["title"])
            save_code_trust(folder, True)

            current = json.loads(self.description_path(folder).read_text(encoding="utf-8"))
            self.assertEqual("Legacy Place", current["title"])
            self.assertEqual({"kept": True}, current["future"])
            self.assertTrue(current["trust-runnable-code"])
            self.assertTrue(legacy.exists())

    def test_image_import_is_content_addressed_and_resize_is_cached(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "place"
            folder.mkdir()
            source = root / "sunset.png"
            Image.new("RGB", (640, 320), "#336699").save(source)

            image_item = import_image_file(folder, source, 25, 35)
            save_map_images(folder, [image_item])
            model = inspect_folder(folder)
            asset = folder / ".living-folder" / "images" / image_item["asset"]
            cache = get_cached_image_path(folder, image_item)

            self.assertTrue(asset.exists())
            self.assertEqual(64, len(asset.stem))
            self.assertEqual(
                asset.stem,
                hashlib.sha256(asset.read_bytes()).hexdigest(),
            )
            self.assertTrue(cache.exists())
            self.assertEqual([image_item], model["map-images"])
            with Image.open(cache) as rendered:
                self.assertEqual(
                    (image_item["width"], image_item["height"]),
                    rendered.size,
                )

    def test_clipboard_image_is_stored_as_hashed_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image = Image.new("RGBA", (80, 60), (255, 0, 0, 128))

            image_item = import_clipboard_image(folder, image, 10, 20)
            asset = folder / ".living-folder" / "images" / image_item["asset"]

            self.assertTrue(asset.exists())
            self.assertEqual(".png", asset.suffix)
            self.assertEqual(
                asset.stem,
                hashlib.sha256(asset.read_bytes()).hexdigest(),
            )
            self.assertEqual((80, 60), (image_item["width"], image_item["height"]))

    def test_map_z_order_is_normalized_and_persisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "alpha.txt").write_text("alpha", encoding="utf-8")
            text = {
                "id": "note-1",
                "text": "note",
                "x": 1,
                "y": 2,
                "alignment": "left",
                "font-size": "small",
                "color": "white",
            }
            save_map_texts(folder, [text])
            save_map_z_order(folder, ["text:note-1", "entry:alpha.txt"])

            model = inspect_folder(folder)

            self.assertEqual(
                ["text:note-1", "entry:alpha.txt"],
                model["map-z-order"],
            )

    def test_temporal_folder_is_inferred_from_coherent_iso_date_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for day in ["2026-06-08", "2026-06-11", "2026-06-12", "2026-06-13"]:
                (folder / day).mkdir()
            (folder / "timesheets.txt").write_text("summary", encoding="utf-8")

            model = inspect_folder(folder)

            self.assertEqual("temporal", model["inferred-presentation"])
            self.assertEqual("temporal", model["active-presentation"])
            self.assertEqual("day", model["temporal"]["resolution"])
            self.assertEqual("2026-06-13", model["temporal"]["most-recent-date"])
            self.assertEqual(4, len(model["temporal"]["nodes"]))
            self.assertEqual(
                "2026-06-08",
                model["temporal"]["nodes"][0]["canonical"][0]["entry"]["name"],
            )
            self.assertEqual(
                ["timesheets.txt"],
                [
                    item["entry"]["name"]
                    for item in model["temporal"]["exceptions"]
                ],
            )

    def test_temporal_model_gathers_associated_artifacts_without_moving_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "2026-06-20").mkdir()
            (folder / "notes-2026-06-20.md").write_text("notes", encoding="utf-8")
            (folder / "build_2026-06-20.zip").write_bytes(b"zip")
            (folder / "scratch.txt~").write_text("backup", encoding="utf-8")

            model = inspect_folder(folder)
            node = model["temporal"]["node-by-date"]["2026-06-20"]

            self.assertEqual(1, len(node["canonical"]))
            self.assertEqual(
                {"notes-2026-06-20.md", "build_2026-06-20.zip"},
                {
                    item["entry"]["name"]
                    for item in node["associated"]
                },
            )
            self.assertEqual(
                ["scratch.txt~"],
                [item["name"] for item in model["temporal"]["hidden"]],
            )

    def test_temporal_matching_rejects_invalid_calendar_dates(self):
        self.assertEqual(
            ["2026-02-28"],
            extract_iso_days("bad-2026-02-30_good-2026-02-28.txt"),
        )

    def test_new_directory_map_entries_arrive_in_incoming(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "new-notes.md").write_text("hello", encoding="utf-8")
            (folder / "new-folder").mkdir()

            model = inspect_folder(folder)

            self.assertEqual([], model["map-entries"])
            self.assertEqual(
                {"new-notes.md", "new-folder"},
                {entry["name"] for entry in model["map-incoming"]},
            )

    def test_placed_ignored_and_missing_map_entries_reconcile(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            placed = folder / "placed.txt"
            ignored = folder / "ignored.txt"
            placed.write_text("placed", encoding="utf-8")
            ignored.write_text("ignored", encoding="utf-8")
            save_map_entry_states(
                folder,
                {
                    "placed.txt": {
                        "state": "placed",
                        "kind": "file",
                        "visual-kind": "text",
                    },
                    "ignored.txt": {
                        "state": "ignored",
                        "kind": "file",
                        "visual-kind": "text",
                    },
                },
            )

            model = inspect_folder(folder)
            self.assertEqual(["placed.txt"], [item["name"] for item in model["map-entries"]])
            self.assertEqual([], model["map-incoming"])
            self.assertEqual(["ignored.txt"], [item["name"] for item in model["map-ignored"]])

            placed.unlink()
            model = inspect_folder(folder)

            self.assertTrue(model["map-entries"][0]["missing"])
            self.assertEqual("text", model["map-entries"][0]["visual-kind"])

    def test_legacy_map_geometry_migrates_to_placed_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "old-map.txt").write_text("old", encoding="utf-8")
            save_map_geometry(
                folder,
                {
                    "old-map.txt": {
                        "x": 10,
                        "y": 20,
                        "width": 120,
                        "height": 70,
                    }
                },
            )

            model = inspect_folder(folder)

            self.assertEqual(["old-map.txt"], [item["name"] for item in model["map-entries"]])
            self.assertEqual("placed", model["map-entry-states"]["old-map.txt"]["state"])


if __name__ == "__main__":
    unittest.main()
