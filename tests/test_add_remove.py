import copy
from pathlib import Path
import tempfile
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QMenu
from playlist import Playlist
import test_editing


class AddRemoveTests(test_editing.EditingWindowTests):
    def test_add_song_and_category_before_target(self):
        original = copy.deepcopy(self.window.document.data)
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(Path("חדש.WRK").resolve()), "")):
            self.window.build_context_menu(2).actions()[0].trigger()
        entries = self.window.document.data["entries"]
        self.assertEqual(entries[2]["path"], str(Path("חדש.WRK").resolve()))
        self.assertEqual(self.map.entries[2].name, "חדש")
        self.assertEqual(entries[3], original["entries"][2])
        self.assertEqual(entries[2]["mixer_levels"], [127] * 16)
        with patch.object(QInputDialog, "getText", return_value=("  פסטיבל חדש  ", True)):
            self.window.build_context_menu(2).actions()[1].trigger()
        self.assertTrue(entries[2]["is_category"])
        self.assertEqual(entries[2]["path"], "")
        self.assertEqual(entries[2]["title"], "פסטיבל חדש")
        self.assertIsNone(self.map.entries[2].number)
        self.assertEqual([e.number for e in self.map.entries if not e.category], list(range(1, 7)))
        self.assertEqual({k: v for k, v in self.window.document.data.items() if k != "entries"},
                         {k: v for k, v in original.items() if k != "entries"})

    def test_remove_selected_songs_keeps_source_files(self):
        with tempfile.TemporaryDirectory() as folder:
            songs = [Path(folder) / f"{i}.WRK" for i in range(2)]
            for song in songs:
                song.write_bytes(b"original music")
                self.window.document.insert_entry(0, song_path=str(song))
            self.window.refresh_after_edit()
            self.click(0)
            self.click(1, Qt.ControlModifier)
            self.window.build_context_menu(0).actions()[-1].trigger()
            self.assertEqual([e.name for e in self.map.entries], ["A", "B", "Festival", "C", "D", "E"])
            for song in songs:
                self.assertEqual(song.read_bytes(), b"original music")
            self.assertEqual(self.map.selected, set())

    def test_remove_category_confirmation_preserves_following_songs(self):
        original = copy.deepcopy(self.window.document.data)
        menu = self.window.build_context_menu(2)
        self.assertEqual([a.text() for a in menu.actions()], ["Add Song", "Add Category", "", "Remove Category"])
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            menu.actions()[-1].trigger()
        self.assertEqual(self.window.document.data, original)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            menu.actions()[-1].trigger()
        self.assertEqual(self.window.document.data["entries"], original["entries"][:2] + original["entries"][3:])
        self.assertEqual([e.number for e in self.map.entries], [1, 2, 3, 4, 5])

    def test_context_click_selection_policy(self):
        self.map.contextRequested.disconnect()
        requested = []
        self.map.contextRequested.connect(lambda index, position: requested.append(index))
        self.click(0)
        self.click(4, Qt.ControlModifier)
        for index, expected in [(0, {0, 4}), (2, {0, 4}), (3, {3})]:
            position = self.position(index)
            event = QContextMenuEvent(QContextMenuEvent.Mouse, position, self.map.mapToGlobal(position))
            self.map.contextMenuEvent(event)
            self.assertEqual(requested[-1], index)
            self.assertEqual(self.map.selected, expected)
        self.window.build_context_menu(3).actions()[-1].trigger()
        self.assertEqual([e.name for e in self.map.entries], ["A", "B", "Festival", "D", "E"])

    def test_cancel_add_and_invalid_remove_are_unchanged(self):
        original = copy.deepcopy(self.window.document.data)
        with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
            self.window.add_song(0)
        for value in [("", True), ("  ", True), ("Cancelled", False)]:
            with patch.object(QInputDialog, "getText", return_value=value):
                self.window.add_category(0)
        self.assertEqual(self.window.document.data, original)
        with self.assertRaises(ValueError):
            self.window.document.remove_entries([0, 2])
        self.assertEqual(self.window.document.data, original)

    def test_save_reload_after_add_remove_and_drag_both_directions(self):
        for rtl in (False, True):
            self.window.document = test_editing.fixture()
            self.window.refresh_after_edit()
            self.window.area.set_column_direction(rtl)
            self.window.document.insert_entry(0, song_path="C:/music/חדש.mid")
            self.window.document.insert_entry(1, category_name="קטגוריה חדשה")
            self.window.refresh_after_edit()
            self.window.remove_songs([2])
            self.drag_with_qt_events(0, self.position(len(self.map.entries) - 1, 0.9))
            self.assertEqual(self.map.entries[-1].name, "חדש")
            expected = copy.deepcopy(self.window.document.data)
            with tempfile.TemporaryDirectory() as folder:
                filename = Path(folder) / "ערוך.json"
                self.assertTrue(self.window.save_to(filename))
                self.assertEqual(Playlist.load(filename).data, expected)
                self.window.load_playlist(filename)
                self.assertEqual(self.window.document.data, expected)
            self.assertEqual(self.map.right_to_left, rtl)
        Path("test-output").mkdir(exist_ok=True)
        self.window.grab().save("test-output/centered-categories.png")

    def test_empty_playlist_can_add_again(self):
        self.window.document.data["entries"].clear()
        self.window.refresh_after_edit()
        menu = self.window.build_context_menu(0)
        self.assertFalse(menu.actions()[-1].isEnabled())
        with patch.object(QInputDialog, "getText", return_value=("ראשונה", True)):
            menu.actions()[1].trigger()
        self.assertEqual(len(self.map.entries), 1)
        self.assertTrue(self.map.entries[0].category)
