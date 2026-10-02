import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from app import MainWindow
from playlist import Playlist
from test_editing import fixture


class SaveAndFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.source = Path(self.folder.name) / "מקור.json"
        fixture().save(self.source)
        self.window = MainWindow(settings=QSettings(
            str(Path(self.folder.name) / "settings.ini"), QSettings.IniFormat))
        self.window.load_playlist(self.source)
        self.window.resize(1920, 1080)
        self.window.show()
        self.app.processEvents()
        Path("test-output").mkdir(exist_ok=True)

    def tearDown(self):
        self.window.close()
        self.folder.cleanup()

    def test_save_after_move_preserves_all_fields_and_order(self):
        original = copy.deepcopy(self.window.document.data)
        self.window.move_songs([4, 0], 6)
        expected = copy.deepcopy(self.window.document.data)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as confirmation:
            self.assertTrue(self.window.save_playlist())
            confirmation.assert_called_once()
            self.assertEqual(confirmation.call_args.args[-1], QMessageBox.No)
            self.assertTrue(self.window.save_playlist())
            confirmation.assert_called_once()
        self.assertEqual(Playlist.load(self.source).data, expected)
        self.assertEqual(expected["entries"], [original["entries"][i] for i in [1, 2, 3, 5, 0, 4]])
        self.window.load_playlist(self.source)
        self.assertEqual(self.window.document.data, expected)
        self.assertEqual([e.number for e in self.window.area.map.entries], [1, None, 2, 3, 4, 5])
        self.assertTrue(self.window.save_playlist())  # approval persists across reloads in this session

    def test_save_declined_and_failed_are_safe(self):
        before = self.source.read_bytes()
        self.window.move_songs([0], 6)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.assertFalse(self.window.save_playlist())
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.window.overwrite_approved, set())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes), \
                patch("playlist.os.replace", side_effect=OSError("disk error")), \
                patch.object(QMessageBox, "warning") as warning:
            self.assertFalse(self.window.save_playlist())
            warning.assert_called_once()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(list(self.source.parent.glob(".cockpit-*.tmp")), [])
        self.assertEqual(self.window.overwrite_approved, set())

    def test_save_as_new_file_and_subsequent_save(self):
        before = self.source.read_bytes()
        self.window.move_songs([0, 4], 3)
        expected = copy.deepcopy(self.window.document.data)
        target = self.source.parent / "עותק"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")), \
                patch.object(QMessageBox, "question") as confirmation:
            self.assertTrue(self.window.save_as_playlist())
            confirmation.assert_not_called()
        target = target.with_suffix(".json")
        self.assertEqual(self.window.document.source, target)
        self.assertEqual(Playlist.load(target).data, expected)
        self.assertEqual(self.source.read_bytes(), before)
        self.window.move_songs([0], 6)
        self.assertTrue(self.window.save_playlist())
        self.assertEqual(self.source.read_bytes(), before)

    def test_save_as_existing_and_cancel(self):
        target = self.source.parent / "existing.json"
        target.write_text('{"entries":[],"name":"existing"}', encoding="utf-8")
        before = target.read_bytes()
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")), \
                patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.assertFalse(self.window.save_as_playlist())
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.window.document.source, self.source)
        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.assertFalse(self.window.save_as_playlist())

    def test_first_overwrite_confirmation_in_new_session(self):
        second = MainWindow()
        second.load_playlist(self.source)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No) as confirmation:
            self.assertFalse(second.save_playlist())
            confirmation.assert_called_once()
        second.close()

    def test_exact_decimal_and_hebrew_roundtrip(self):
        self.source.write_text('{"name":"עברית","unknown":0.12345678901234567890123456789,'
            '"huge":123456789012345678901234567890,"entries":[{"path":"שיר.mid",'
            '"value":1.234567890123456789e-50,"is_category":false}]}', encoding="utf-8")
        document = Playlist.load(self.source)
        expected = copy.deepcopy(document.data)
        target = self.source.parent / "exact.json"
        document.save(target)
        self.assertEqual(Playlist.load(target).data, expected)
        self.assertIn('"עברית"', target.read_text(encoding="utf-8"))
        self.assertIn("0.12345678901234567890123456789", target.read_text(encoding="utf-8"))

    def test_font_menu_and_keyboard_shortcuts(self):
        self.window.activateWindow()
        self.window.setFocus()
        QTest.qWait(100)
        QTest.keyClick(self.window, Qt.Key_Equal, Qt.ControlModifier)
        self.assertEqual(self.window.area.map.font().pointSize(), 11)
        QTest.keyClick(self.window, Qt.Key_Minus, Qt.ControlModifier)
        self.assertEqual(self.window.area.map.font().pointSize(), 10)
        self.window.change_font_size(4)
        QTest.keyClick(self.window, Qt.Key_0, Qt.ControlModifier)
        self.assertEqual(self.window.area.map.font().pointSize(), 10)

    def test_font_sizes_reflow_preserve_selection_and_document(self):
        self.window.document = Playlist({"entries": [
            {"path": f"שיר {i}.mid", "is_category": i % 15 == 0, "title": "קטגוריה"}
            for i in range(179)]}, self.source)
        self.window.area.set_entries(self.window.document.display_entries())
        view = self.window.area.map
        view.selected = {1, 3}
        view.anchor = 1
        original = copy.deepcopy(self.window.document.data)
        initial = view.geometry_plan
        initial_height = view.row_height
        plans = []
        capacities = []
        for size in [6, 10, 16, 24, 32]:
            view.set_font_size(size)
            self.window.area.reflow()
            self.app.processEvents()
            plan = view.geometry_plan
            plans.append(plan)
            capacities.append(self.window.area.viewport().height() // view.row_height)
            self.assertGreaterEqual(plan.columns * plan.rows, 179)
            self.assertEqual(view.selected, {1, 3})
            self.assertEqual(view.anchor, 1)
            self.assertEqual(self.window.document.data, original)
            self.assertEqual(view.font().pointSize(), size)
            self.window.grab().save(f"test-output/font-{size}.png")
        self.assertGreater(view.row_height, initial_height)
        self.assertLess(plans[0].column_width, initial.column_width)
        self.assertGreater(plans[-1].column_width, plans[0].column_width)
        self.assertLess(capacities[-1], capacities[0])
        self.window.change_font_size(reset=True)
        self.assertEqual(view.font().pointSize(), 10)
        self.assertEqual(view.geometry_plan, initial)
        self.window.change_font_size(1)
        self.assertEqual(view.font().pointSize(), 11)
        self.window.change_font_size(-1)
        self.assertEqual(view.font().pointSize(), 10)

    @unittest.skipUnless(os.environ.get("COCKPIT_TEST_PLAYLIST"), "Set COCKPIT_TEST_PLAYLIST")
    def test_real_playlist_copy_save_and_save_as(self):
        real_source = Path(os.environ["COCKPIT_TEST_PLAYLIST"])
        checksum = hashlib.sha256(real_source.read_bytes()).hexdigest()
        self.source.write_bytes(real_source.read_bytes())
        self.window.load_playlist(self.source)
        original = copy.deepcopy(self.window.document.data)
        self.window.move_songs([11, 13, 15], 150)
        expected = copy.deepcopy(self.window.document.data)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.assertTrue(self.window.save_playlist())
        self.window.load_playlist(self.source)
        self.assertEqual(self.window.document.data, expected)
        target = self.source.parent / "נשמר.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")):
            self.assertTrue(self.window.save_as_playlist())
        self.assertEqual(Playlist.load(target).data, expected)
        self.assertEqual(sorted(expected["entries"], key=str), sorted(original["entries"], key=str))
        self.assertEqual(hashlib.sha256(real_source.read_bytes()).hexdigest(), checksum)
