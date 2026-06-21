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
        model = {"folder": "C:/second"}

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


if __name__ == "__main__":
    unittest.main()
