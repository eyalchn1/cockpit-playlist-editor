import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from PySide6.QtWidgets import QApplication
from playlist import Playlist
from layout import calculate_layout
from app import MainWindow


class PrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_projection_preserves_all_data(self):
        data = {"name": "בדיקה", "unknown": {"value": [1, 2]}, "entries": [
            {"path": "..\\שירים\\המלח שלי.WRK", "title": "Guitar", "is_category": False, "extra": [7]},
            {"title": "קטגוריה", "is_category": True},
            {"path": "/music/song.mid", "is_category": False}]}
        original = copy.deepcopy(data)
        document = Playlist(data, Path("test.json"))
        entries = document.display_entries()
        self.assertEqual([e.name for e in entries], ["המלח שלי", "קטגוריה", "song"])
        self.assertEqual([e.number for e in entries], [1, None, 2])
        self.assertEqual(document.data, original)

    def test_invalid_structure(self):
        for value in ([], {}, {"entries": [None]}, {"entries": [{"is_category": "false"}]}):
            with self.assertRaises(ValueError):
                Playlist(value, Path("test.json"))

    def test_layout(self):
        for width, height in [(1900, 900), (800, 500), (300, 80)]:
            plan = calculate_layout(210, width, height, 28, 190)
            self.assertGreaterEqual(plan.rows * plan.columns, 210)
            self.assertLessEqual(plan.rows * 28, height)
            self.assertGreaterEqual(plan.column_width, 190)
        plan = calculate_layout(210, 1900, 900, 28, 190)
        self.assertEqual(plan.columns, 10)
        self.assertLessEqual(plan.content_width, 1900)

    def test_bom_empty_playlist(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "empty.json"
            filename.write_text('{"name":"Empty","entries":[],"other":42}', encoding="utf-8-sig")
            document = Playlist.load(filename)
            self.assertEqual(document.display_entries(), [])
            self.assertEqual(document.data["other"], 42)

    @unittest.skipUnless(os.environ.get("COCKPIT_TEST_PLAYLIST"), "Set COCKPIT_TEST_PLAYLIST for real-file UI test")
    def test_real_playlist_window(self):
        source = Path(os.environ["COCKPIT_TEST_PLAYLIST"])
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        window = MainWindow()
        self.assertTrue(window.load_playlist(source))
        original = copy.deepcopy(window.document.data)
        window.resize(1920, 1080)
        window.show()
        self.app.processEvents()
        entries = window.area.map.entries
        self.assertEqual(len(entries), len(original["entries"]))
        self.assertEqual([e.index for e in entries], list(range(len(entries))))
        self.assertEqual([e.number for e in entries if not e.category], list(range(1, sum(not e.category for e in entries) + 1)))
        output = Path("test-output")
        output.mkdir(exist_ok=True)
        window.grab().save(str(output / "full-hd.png"))
        print(f"REAL FILE: {sum(not e.category for e in entries)} songs, {sum(e.category for e in entries)} categories; {window.area.map.geometry_plan}")
        window.resize(800, 500)
        self.app.processEvents()
        self.assertGreater(window.area.map.width(), window.area.viewport().width())
        window.grab().save(str(output / "small-window.png"))
        self.assertEqual(window.document.data, original)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        window.close()


if __name__ == "__main__":
    unittest.main()
