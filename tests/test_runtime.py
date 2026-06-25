import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from livingfolders import runtime


class RuntimeTests(unittest.TestCase):
    def test_launcher_installs_into_machine_root_path_dir(self):
        with tempfile.TemporaryDirectory() as temporary:
            launcher_dir = Path(temporary)
            with mock.patch.object(
                runtime,
                "resolve_launcher_dir",
                return_value=launcher_dir,
            ):
                path = runtime.install_launcher()

            self.assertEqual(launcher_dir / runtime.LAUNCHER_NAME, path)
            self.assertIn(
                "from livingfolders.runtime import launcher_main",
                path.read_text(encoding="utf-8"),
            )

    def test_launcher_accepts_optional_folder_argument(self):
        with mock.patch.object(runtime, "launch_or_summon") as launch:
            runtime.launcher_main(["C:/wanted"])
            launch.assert_called_once_with("C:/wanted")

        with mock.patch.object(runtime, "launch_or_summon") as launch:
            with mock.patch.object(runtime.Path, "cwd", return_value=Path("C:/here")):
                runtime.launcher_main([])
            launch.assert_called_once_with(Path("C:/here"))

    def test_lock_file_and_summons_channel(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with (
                mock.patch.object(runtime, "resolve_runtime_home", return_value=home),
            ):
                first = runtime.acquire_instance()
                second = runtime.acquire_instance()
                self.assertIsNotNone(first)
                self.assertIsNone(second)

                lock = runtime.read_lock()
                self.assertEqual(first["lock_id"], lock["lock_id"])
                self.assertEqual(first["pid"], lock["pid"])
                self.assertEqual("open", lock["command"])

                path = runtime.send_summons("C:/")
                self.assertTrue(path.exists())
                messages = runtime.consume_summons()
                self.assertEqual("summon", messages[0]["type"])
                self.assertFalse(path.exists())

                runtime.release_instance(first)
                self.assertFalse((home / runtime.CLI_PROJECT_DIR_NAME / runtime.LOCK_NAME).exists())

    def test_release_does_not_remove_another_instances_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            path = home / runtime.CLI_PROJECT_DIR_NAME / runtime.LOCK_NAME
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"lock_id": "someone-else"}), encoding="utf-8")
            instance = {
                "lock_id": "mine",
                "lock-path": str(path),
            }

            runtime.release_instance(instance)
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
