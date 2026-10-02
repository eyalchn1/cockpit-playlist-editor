import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication

from playlist import Playlist, DisplayEntry
from view import MapArea


class HierarchyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Root"
        self.root.mkdir()
        folder = self.root
        for depth in range(4):
            (folder / f"song{depth}.mid").write_bytes(b"song")
            if depth < 3:
                folder = folder / f"Level{depth + 1}"
                folder.mkdir()
        self.doc = Playlist({"name": "Hierarchy", "entries": []}, None)

    def tearDown(self):
        self.temp.cleanup()

    def test_recursive_depth_and_song_entries(self):
        self.doc.import_folders([self.root], 0, include_subfolders=True)
        self.assertEqual([e.depth for e in self.doc.display_entries() if e.category], [0, 1, 2, 3])
        self.assertEqual([e.number for e in self.doc.display_entries() if not e.category], [1, 2, 3, 4])
        self.assertTrue(all("hierarchy_depth" not in e for e in self.doc.data["entries"] if not e["is_category"]))

    def test_first_level_and_manual_category_default_depth(self):
        self.doc.import_folders([self.root], 0)
        self.doc.insert_entry(0, category_name="Manual")
        self.assertEqual([e.depth for e in self.doc.display_entries()], [0, 0, 0])
        self.assertTrue(all("hierarchy_depth" not in e for e in self.doc.data["entries"]))

    def test_save_reload_and_song_moves_preserve_depth(self):
        self.doc.import_paths([self.root], 0, include_subfolders=True)
        categories = [copy.deepcopy(e) for e in self.doc.data["entries"] if e["is_category"]]
        self.doc.move_songs([1, 3], len(self.doc.data["entries"]))
        self.assertEqual([e for e in self.doc.data["entries"] if e["is_category"]], categories)
        destination = Path(self.temp.name) / "hierarchy.json"
        self.doc.save(destination)
        loaded = Playlist.load(destination)
        self.assertEqual(loaded.data, self.doc.data)
        self.assertEqual([e.depth for e in loaded.display_entries() if e.category], [0, 1, 2, 3])

    def test_multiple_roots_restart_depth(self):
        self.doc.import_folders([self.root, self.root], 0, include_subfolders=True)
        self.assertEqual([e.depth for e in self.doc.display_entries() if e.category], [0, 1, 2, 3] * 2)

    def test_legacy_and_invalid_depth_load_safely(self):
        for value in (None, -1, True, "2", 1.5):
            entry = {"is_category": True, "title": "Legacy"}
            if value is not None:
                entry["hierarchy_depth"] = value
            doc = Playlist({"entries": [entry]}, None)
            self.assertEqual(doc.display_entries()[0].depth, 0)

    def test_category_widths_and_direction_anchors(self):
        area = MapArea()
        try:
            rect = QRect(10, 20, 200, 24)
            for rtl in (False, True):
                area.map.right_to_left = rtl
                bars = [area.map.category_rect(rect, depth) for depth in (0, 1, 2, 3, 100)]
                self.assertEqual([bar.width() for bar in bars], [200, 160, 120, 120, 120])
                self.assertEqual(bars[0], rect)
                for bar in bars:
                    self.assertEqual(bar.right() if rtl else bar.left(), rect.right() if rtl else rect.left())
                    self.assertEqual(bar.top(), rect.top())
                    self.assertEqual(bar.height(), rect.height())
        finally:
            area.close()

    def test_category_text_centering_and_existing_elision(self):
        area = MapArea()
        area.resize(420, 300)
        area.map.column_width_override = 400
        area.show()
        self.app.processEvents()
        try:
            for rtl in (False, True):
                area.set_column_direction(rtl)
                for name in ("Category", "קטגוריה", "Long category title " * 30, "קטגוריה ארוכה " * 30):
                    area.set_entries([DisplayEntry(i, name, None, True, i) for i in range(4)])
                    calls = []

                    class RecordingPainter(QPainter):
                        def drawText(self, rect, alignment, text):
                            calls.append((QRect(rect), alignment, text))
                            return super().drawText(rect, alignment, text)

                    with patch("view.QPainter", RecordingPainter):
                        area.map.grab()
                    font = QFont(area.map.font())
                    font.setBold(True)
                    metrics = QFontMetrics(font, area.map)
                    self.assertEqual(len(calls), 4)
                    for depth, (text_rect, alignment, text) in enumerate(calls):
                        row = QRect(4, depth * area.map.row_height + 2, 392, area.map.row_height - 4)
                        bar = area.map.category_rect(row, depth)
                        self.assertEqual(text_rect, bar.adjusted(7, 0, -7, 0))
                        self.assertEqual(alignment, Qt.AlignCenter)
                        label = metrics.elidedText(name, Qt.ElideLeft, text_rect.width())
                        prefix = "\u200f" if not depth or rtl else "\u200e"
                        self.assertEqual(text, prefix + label)
        finally:
            area.close()

    def test_rendered_background_matches_depth_and_direction(self):
        area = MapArea()
        area.resize(420, 300)
        area.map.column_width_override = 400
        area.show()
        self.app.processEvents()
        try:
            for rtl in (False, True):
                area.set_column_direction(rtl)
                area.set_entries([DisplayEntry(i, "Category", None, True, i) for i in range(4)])
                image = area.map.grab().toImage()
                for depth in range(4):
                    row = QRect(4, depth * area.map.row_height + 2, 392, area.map.row_height - 4)
                    bar = area.map.category_rect(row, depth)
                    y = row.top() + 1  # Above text, inside the painted background.
                    self.assertEqual(image.pixelColor(bar.left(), y), QColor("#254d59"))
                    self.assertEqual(image.pixelColor(bar.right(), y), QColor("#254d59"))
                    if depth:
                        outside = bar.left() - 1 if rtl else bar.right() + 1
                        self.assertEqual(image.pixelColor(outside, y), QColor("#101923"))
        finally:
            area.close()
