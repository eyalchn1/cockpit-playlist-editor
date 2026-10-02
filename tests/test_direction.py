import copy
from pathlib import Path
import tempfile
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from app import MainWindow
import test_editing


class RightToLeftTests(test_editing.EditingWindowTests):
    """Run the existing click, drag, drop, boundary and real-file tests mirrored."""
    def setUp(self):
        super().setUp()
        self.folder = tempfile.TemporaryDirectory()
        self.settings_file = str(Path(self.folder.name) / "preferences.ini")
        self.window.settings = QSettings(self.settings_file, QSettings.IniFormat)
        self.window.area.set_column_direction(True)
        self.window.update_direction_labels()

    def tearDown(self):
        super().tearDown()
        self.folder.cleanup()

    def test_toggle_is_visual_only_and_persists(self):
        original = copy.deepcopy(self.window.document.data)
        self.map.selected = {0, 4}
        plan = self.map.geometry_plan
        QTest.mouseClick(self.window.direction_button, Qt.LeftButton)
        self.assertFalse(self.map.right_to_left)
        QTest.mouseClick(self.window.direction_button, Qt.LeftButton)
        self.assertTrue(self.map.right_to_left)
        self.assertEqual(self.map.geometry_plan, plan)
        self.assertEqual(self.map.selected, {0, 4})
        self.assertEqual(self.window.document.data, original)
        reopened = MainWindow(settings=QSettings(self.settings_file, QSettings.IniFormat))
        self.assertTrue(reopened.area.map.right_to_left)
        reopened.close()

    def test_font_resize_then_drop_in_rtl(self):
        original = copy.deepcopy(self.window.document.data)
        for size in (6, 16, 24, 10):
            self.map.set_font_size(size)
            self.window.area.reflow()
            self.app.processEvents()
            for index in range(len(self.map.entries)):
                self.assertEqual(self.map.index_at(self.position(index)), index)
                self.assertEqual(self.map.boundary_at(self.position(index, 0.1))[0], index)
                self.assertEqual(self.map.boundary_at(self.position(index, 0.9))[0], index + 1)
            self.assertEqual(self.window.document.data, original)
        self.drag_with_qt_events(0, self.position(2, 0.9), screenshot=True)
        self.assertEqual([e.name for e in self.map.entries], ["B", "Festival", "A", "C", "D", "E"])
        self.assertTrue(self.map.right_to_left)
        Path("test-output").mkdir(exist_ok=True)
        self.window.grab().save("test-output/right-to-left.png")

    def test_rtl_scroll_start_and_empty_space(self):
        self.window.resize(500, 350)
        self.map.set_font_size(32)
        self.window.area.reflow()
        self.window.area.scroll_to_start()
        bar = self.window.area.horizontalScrollBar()
        self.assertEqual(bar.value(), bar.maximum())
        self.window.area.set_column_direction(False)
        self.assertEqual(bar.value(), 0)
