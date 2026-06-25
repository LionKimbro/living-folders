import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_pythonw_launcher_uses_stable_execroot_and_open_at(self):
        path = ROOT / "launchers" / "living-folders.bat"
        text = path.read_text(encoding="utf-8")

        self.assertIn("set RUNTIME_ROOT=C:\\lion\\runtime\\living-folders", text)
        self.assertIn('pythonw -m livingfolders --execroot "%RUNTIME_ROOT%"', text)
        self.assertIn('--execpath.open-at "%~1"', text)

    def test_debug_launcher_uses_python_and_open_at(self):
        path = ROOT / "launchers" / "living-folders-debug.bat"
        text = path.read_text(encoding="utf-8")

        self.assertIn("set RUNTIME_ROOT=C:\\lion\\runtime\\living-folders", text)
        self.assertIn('python -m livingfolders --execroot "%RUNTIME_ROOT%"', text)
        self.assertIn('--execpath.open-at "%~1"', text)


if __name__ == "__main__":
    unittest.main()
