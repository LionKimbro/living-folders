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


if __name__ == "__main__":
    unittest.main()
