import copy
from pathlib import Path
import tempfile
from unittest.mock import patch
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from app import MainWindow
from help_ui import show_help_dialog, shortcut_html
import test_editing


class PolishTests(test_editing.EditingWindowTests):
    def test_playlist_directory_restored_next_session(self):
        target = Path(self.folder.name) / "playlist.json"
        self.assertTrue(self.window.save_to(target))
        reopened = MainWindow(settings=QSettings(self.preferences, QSettings.IniFormat))
        with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")) as picker:
            reopened.open_dialog()
            self.assertEqual(picker.call_args.args[2], str(target.parent))
        self.assertTrue(reopened.load_playlist(target))
        self.assertEqual(reopened.settings.value("files/playlistDirectory"), str(target.parent))
        reopened.close()

    def setUp(self):
        super().setUp()
        self.folder = tempfile.TemporaryDirectory()
        self.preferences = str(Path(self.folder.name) / "view.ini")
        self.window.settings = QSettings(self.preferences, QSettings.IniFormat)
        self.map.column_width_override = None
        self.window.area.reflow()

    def tearDown(self):
        super().tearDown()
        self.folder.cleanup()

    def test_width_shortcuts_reset_and_persistence(self):
        initial = self.map.geometry_plan
        self.window.activateWindow()
        self.window.setFocus()
        QTest.qWait(100)
        QTest.keyClick(self.window, Qt.Key_Right, Qt.ControlModifier)
        wider = self.map.geometry_plan.column_width
        self.assertGreater(wider, initial.column_width)
        QTest.keyClick(self.window, Qt.Key_Left, Qt.ControlModifier)
        self.assertEqual(self.map.geometry_plan.column_width, initial.column_width)
        self.window.change_column_width(48)
        reopened = MainWindow(settings=QSettings(self.preferences, QSettings.IniFormat))
        self.assertEqual(reopened.area.map.column_width_override, self.map.column_width_override)
        reopened.close()
        QTest.keyClick(self.window, Qt.Key_Down, Qt.ControlModifier)
        self.assertIsNone(self.map.column_width_override)
        self.assertEqual(self.map.geometry_plan, initial)

    def test_width_font_direction_selection_and_drag(self):
        original = copy.deepcopy(self.window.document.data)
        self.click(0)
        self.click(1, Qt.ControlModifier)
        for rtl in (True, False):
            self.window.area.set_column_direction(rtl)
            for size in (6, 16, 24, 10):
                self.window.change_font_size(reset=True)
                self.window.change_font_size(size - 10)
                for width in (144, 240, 480):
                    self.map.column_width_override = width
                    self.window.area.reflow()
                    self.assertEqual(self.map.geometry_plan.column_width, width)
                    self.assertEqual(self.map.selected, {0, 1})
                    self.assertEqual(self.window.document.data, original)
                    for index in range(len(self.map.entries)):
                        self.assertEqual(self.map.index_at(self.position(index)), index)
        self.drag_with_qt_events(0, self.position(4, 0.9))
        self.assertEqual([e.name for e in self.map.entries], ["Festival", "C", "D", "A", "B", "E"])
        self.assertEqual(self.map.selected, {3, 4})

    def test_help_windows_open_offline(self):
        menu = next(a.menu() for a in self.window.menuBar().actions() if a.text() == "Help")
        for action in menu.actions():
            action.trigger()
            self.app.processEvents()
            dialog = self.window.help_dialogs[action.text()]
            self.assertTrue(dialog.isVisible())
            self.assertTrue(dialog.browser.toPlainText())
            Path("test-output").mkdir(exist_ok=True)
            dialog.grab().save("test-output/" + ("about" if "About" in action.text() else
                             "shortcuts" if "Keyboard" in action.text() else "guide") + ".png")
            dialog.close()
        text = shortcut_html(self.window)
        for key in ("Ctrl+Right", "Ctrl+Left", "Ctrl+Down", "Ctrl+S", "Ctrl+O"):
            self.assertIn(key, text)
        self.assertIn("2026 Eyal Cohen", self.window.help_dialogs["About Cockpit Playlist Editor"].browser.toPlainText())

    def test_save_and_reload_with_width_preserves_data(self):
        self.window.change_column_width(72)
        self.window.document.insert_entry(0, category_name="חדש")
        self.window.document.remove_entries([2])
        self.window.refresh_after_edit()
        expected = copy.deepcopy(self.window.document.data)
        target = Path(self.folder.name) / "saved.json"
        self.assertTrue(self.window.save_to(target))
        self.assertTrue(self.window.load_playlist(target))
        self.assertEqual(self.window.document.data, expected)
        self.assertIsNotNone(self.map.column_width_override)
