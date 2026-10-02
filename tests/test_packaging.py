import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from app import MainWindow


class FrozenSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_frozen_preferences_survive_relaunch_beside_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = str(Path(folder) / "Cockpit Playlist Editor.exe")
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", executable):
                window = MainWindow()
                self.assertEqual(Path(window.settings.fileName()), Path(folder) / ".user-settings.ini")
                window.toggle_column_direction()
                window.include_subfolders_action.trigger()
                window.change_column_width(24)
                expected_width = window.area.map.column_width_override
                window.close()
                reopened = MainWindow()
                self.assertTrue(reopened.area.map.right_to_left)
                self.assertTrue(reopened.include_subfolders_action.isChecked())
                self.assertEqual(reopened.area.map.column_width_override, expected_width)
                reopened.close()
