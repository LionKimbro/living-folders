import unittest

from livingfolders.discrete import initial_state, reduce


class DiscreteEngineTests(unittest.TestCase):
    def test_navigation_emits_load_effect_without_reading_filesystem(self):
        state, effects = reduce(
            initial_state(),
            {"type": "NAVIGATE", "path": "C:/somewhere", "remember": True},
        )

        self.assertIsNone(state["folder"])
        self.assertEqual(
            [{"type": "LOAD_FOLDER", "path": "C:/somewhere", "remember": True}],
            effects,
        )

    def test_loaded_folder_enters_history_and_projects(self):
        state = initial_state()
        state["folder"] = "C:/first"
        model = {
            "folder": "C:/second",
            "trust-runnable-code": False,
        }

        state, effects = reduce(
            state,
            {"type": "FOLDER_LOADED", "model": model, "remember": True},
        )

        self.assertEqual(["C:/first"], state["back-stack"])
        self.assertEqual("C:/second", state["folder"])
        self.assertEqual([{"type": "PROJECT"}], effects)

    def test_map_motion_commits_geometry_through_an_effect(self):
        state = initial_state()
        state["folder"] = "C:/map"
        state["model"] = {"map-geometry": {}}
        geometry = {"x": 4, "y": 8, "width": 120, "height": 70}

        state, effects = reduce(
            state,
            {
                "type": "MAP_GEOMETRY_COMMITTED",
                "entry-name": "alpha.txt",
                "geometry": geometry,
            },
        )

        self.assertEqual(geometry, state["model"]["map-geometry"]["alpha.txt"])
        self.assertEqual("WRITE_MAP_GEOMETRY", effects[0]["type"])
        self.assertEqual({"type": "PROJECT_MAP"}, effects[1])

    def test_folder_navigation_restores_each_folders_code_trust(self):
        state = initial_state()
        state["trust-code"] = True

        state, _effects = reduce(
            state,
            {
                "type": "FOLDER_LOADED",
                "model": {
                    "folder": "C:/next",
                    "trust-runnable-code": False,
                },
                "remember": False,
            },
        )

        self.assertFalse(state["trust-code"])

    def test_changing_trust_emits_folder_local_persistence_effect(self):
        state = initial_state()
        state["folder"] = "C:/trusted-place"

        state, effects = reduce(
            state,
            {"type": "SET_TRUST", "value": True},
        )

        self.assertTrue(state["trust-code"])
        self.assertEqual(
            [
                {
                    "type": "SAVE_CODE_TRUST",
                    "folder": "C:/trusted-place",
                    "trusted": True,
                }
            ],
            effects,
        )

    def test_delete_file_is_an_explicit_effect(self):
        state = initial_state()
        state["folder"] = "C:/map"

        _state, effects = reduce(
            state,
            {"type": "DELETE_FILE", "path": "C:/map/old.txt"},
        )

        self.assertEqual(
            [
                {
                    "type": "DELETE_FILE",
                    "folder": "C:/map",
                    "path": "C:/map/old.txt",
                }
            ],
            effects,
        )

    def test_map_text_can_be_created_and_moved(self):
        state = initial_state()
        state["folder"] = "C:/map"
        state["model"] = {"map-texts": [], "map-z-order": []}
        text_item = {
            "id": "note-1",
            "text": "hello",
            "x": 10,
            "y": 20,
            "alignment": "left",
            "font-size": "medium",
            "color": "white",
        }

        state, effects = reduce(
            state,
            {"type": "UPSERT_MAP_TEXT", "text-item": text_item},
        )

        self.assertEqual([text_item], state["model"]["map-texts"])
        self.assertEqual(["text:note-1"], state["model"]["map-z-order"])
        self.assertEqual("WRITE_MAP_TEXTS", effects[0]["type"])

        state, effects = reduce(
            state,
            {"type": "MAP_TEXT_MOVED", "text-id": "note-1", "x": 90, "y": 110},
        )

        self.assertEqual(90, state["model"]["map-texts"][0]["x"])
        self.assertEqual(110, state["model"]["map-texts"][0]["y"])
        self.assertEqual("WRITE_MAP_TEXTS", effects[0]["type"])

    def test_map_image_can_be_added_and_resized(self):
        state = initial_state()
        state["folder"] = "C:/map"
        state["model"] = {"map-images": [], "map-z-order": []}
        image_item = {
            "id": "image-1",
            "asset": "abc.png",
            "source-name": "photo.png",
            "x": 10,
            "y": 20,
            "width": 200,
            "height": 100,
        }

        state, effects = reduce(
            state,
            {"type": "UPSERT_MAP_IMAGE", "image-item": image_item},
        )

        self.assertEqual([image_item], state["model"]["map-images"])
        self.assertEqual(["image:image-1"], state["model"]["map-z-order"])
        self.assertEqual("WRITE_MAP_IMAGES", effects[0]["type"])

        state, effects = reduce(
            state,
            {
                "type": "MAP_IMAGE_GEOMETRY_COMMITTED",
                "image-id": "image-1",
                "geometry": {"x": 40, "y": 50, "width": 300, "height": 220},
            },
        )

        self.assertEqual(300, state["model"]["map-images"][0]["width"])
        self.assertEqual(220, state["model"]["map-images"][0]["height"])
        self.assertEqual("WRITE_MAP_IMAGES", effects[0]["type"])

        state, effects = reduce(
            state,
            {"type": "DELETE_MAP_IMAGE", "image-id": "image-1"},
        )

        self.assertEqual([], state["model"]["map-images"])
        self.assertEqual([], state["model"]["map-z-order"])
        self.assertIsNone(state["selected-image"])
        self.assertEqual("WRITE_MAP_IMAGES", effects[0]["type"])

    def test_page_layer_move_swaps_one_z_order_position(self):
        state = initial_state()
        state["folder"] = "C:/map"
        state["model"] = {
            "map-z-order": [
                "entry:back.txt",
                "text:note",
                "image:front",
            ]
        }

        state, effects = reduce(
            state,
            {
                "type": "MOVE_MAP_LAYER",
                "key": "text:note",
                "direction": 1,
            },
        )

        self.assertEqual(
            ["entry:back.txt", "image:front", "text:note"],
            state["model"]["map-z-order"],
        )
        self.assertEqual("WRITE_MAP_Z_ORDER", effects[0]["type"])

        state, _effects = reduce(
            state,
            {
                "type": "MOVE_MAP_LAYER",
                "key": "text:note",
                "direction": -1,
            },
        )
        self.assertEqual(
            ["entry:back.txt", "text:note", "image:front"],
            state["model"]["map-z-order"],
        )


if __name__ == "__main__":
    unittest.main()
