import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PySide6.QtCore import QSettings, QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from app import MainWindow
from playlist import Playlist
import test_folder_drop
from test_editing import fixture


class StartupTests(unittest.TestCase):
    folder = test_folder_drop.FolderDropTests.folder
    child = test_folder_drop.FolderDropTests.child
    drop_folders = test_folder_drop.FolderDropTests.drop_folders
    names = test_folder_drop.FolderDropTests.names
    position = test_folder_drop.FolderDropTests.position

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = MainWindow(settings=QSettings(str(self.root / "settings.ini"), QSettings.IniFormat))
        self.window.show()
        self.app.processEvents()
        self.map = self.window.area.map

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def song(self, name="one.MID"):
        path = self.root / name
        path.write_bytes(b"original")
        return path

    def test_startup_is_ready_and_context_menu_available(self):
        self.assertIsNone(self.window.document)
        self.assertEqual(self.map.entries, [])
        self.assertTrue(self.map.acceptDrops())
        self.assertFalse(self.window.save_action.isEnabled())
        menu = self.window.build_context_menu(0)
        self.assertEqual([a.text() for a in menu.actions()][:2], ["Add Song", "Add Category"])
        self.assertFalse(menu.actions()[-1].isEnabled())
        popup = MagicMock()
        with patch.object(self.window, "build_context_menu", return_value=popup):
            event = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(50, 50), self.map.mapToGlobal(QPoint(50, 50)))
            self.map.contextMenuEvent(event)
        popup.exec.assert_called_once()

    def test_single_song_drop_uses_add_song_entry(self):
        song = self.song()
        self.drop_folders([song])
        expected = Playlist({"entries": []}, None)
        expected.insert_entry(0, song_path=str(song))
        self.assertEqual(self.window.document.data, expected.data)
        self.assertEqual(self.window.name_label.text(), "Untitled Playlist")
        self.assertEqual(song.read_bytes(), b"original")
        self.assertTrue(self.window.save_action.isEnabled())

    def test_multiple_songs_skip_unsupported(self):
        paths = [self.song("two.wrk"), self.song("ignored.txt"), self.song("one.mIdI")]
        self.drop_folders(paths)
        self.assertEqual(self.names(), ["two", "one"])
        self.assertEqual([e.number for e in self.map.entries], [1, 2])

    def test_folders_from_startup_both_modes(self):
        first = self.folder("First", ["direct.mid"])
        self.child(first, "Child", ["nested.mid"])
        second = self.folder("Second")
        for include in (False, True):
            self.window.document = None
            self.window.area.set_entries([])
            if include:
                self.window.include_subfolders_action.trigger()
            self.drop_folders([first, second])
            self.assertEqual(self.names(), ["First", "direct", "Child", "nested", "Second"]
                             if include else ["First", "direct", "Second"])

    def test_mixed_drop_preserves_item_order(self):
        folder = self.folder("Folder", ["direct.mid"])
        self.child(folder, "Child", ["nested.mid"])
        self.window.include_subfolders_action.trigger()
        self.drop_folders([self.song("before.wrk"), folder, self.song("ignored.txt"), self.song("after.mid")])
        self.assertEqual(self.names(), ["before", "Folder", "direct", "Child", "nested", "after"])

    def test_add_song_from_empty_context_menu(self):
        song = self.song()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(song), "")):
            self.window.build_context_menu(0).actions()[0].trigger()
        self.assertEqual(self.names(), ["one"])
        self.assertIsNone(self.window.document.source)

    def test_add_category_from_empty_context_menu(self):
        with patch.object(QInputDialog, "getText", return_value=("First", True)):
            self.window.build_context_menu(0).actions()[1].trigger()
        self.assertEqual(self.names(), ["First"])
        self.assertIsNone(self.map.entries[0].number)

    def test_cancel_add_keeps_startup_empty(self):
        with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
            self.window.add_song(0)
        with patch.object(QInputDialog, "getText", return_value=("", False)):
            self.window.add_category(0)
        self.assertIsNone(self.window.document)

    def test_first_save_as_name_reload_then_regular_save(self):
        self.drop_folders([self.song(), self.folder("Category")])
        destination = self.root / "My Playlist.json"
        self.assertFalse(destination.exists())
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")) as picker:
            self.assertTrue(self.window.save_playlist())
            picker.assert_called_once()
        data = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "My Playlist")
        self.assertEqual(data, self.window.document.data)
        self.assertEqual(self.window.name_label.text(), "My Playlist")
        with patch.object(QFileDialog, "getSaveFileName") as picker:
            self.assertTrue(self.window.save_playlist())
            picker.assert_not_called()
        self.assertTrue(self.window.load_playlist(destination))
        self.assertEqual(self.names(), ["one", "Category"])

    def test_existing_name_unchanged_by_save_as(self):
        source = self.root / "existing.json"
        fixture().save(source)
        self.window.load_playlist(source)
        self.drop_folders([self.song()], self.position(3, 0.1))
        self.assertEqual(self.names()[3], "one")
        self.assertTrue(self.window.save_to(self.root / "different.json"))
        self.assertEqual(self.window.document.data["name"], "Test")

    def test_mixed_drop_at_existing_boundary_in_both_directions(self):
        folder = self.folder("Folder", ["direct.mid"])
        paths = [self.song("before.mid"), folder, self.song("after.wrk")]
        for rtl in (False, True):
            self.window.document = fixture()
            self.window.refresh_after_edit()
            self.window.area.set_column_direction(rtl)
            self.drop_folders(paths, self.position(3, 0.1))
            self.assertEqual(self.names(), ["A", "B", "Festival", "before", "Folder", "direct",
                                            "after", "C", "D", "E"])

    def test_unsupported_only_does_not_create_document(self):
        self.window.import_paths([self.song("ignored.mp3")], 0)
        self.assertIsNone(self.window.document)
        self.assertFalse(self.window.save_action.isEnabled())

    def test_cancel_first_save_keeps_temporary_name(self):
        self.drop_folders([self.song()])
        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.assertFalse(self.window.save_playlist())
        self.assertIsNone(self.window.document.source)
        self.assertNotIn("name", self.window.document.data)
        self.assertEqual(self.window.name_label.text(), "Untitled Playlist")

    def test_clear_at_startup_is_harmless(self):
        self.window.clear_action.trigger()
        self.assertIsNone(self.window.document)
        self.assertEqual(self.map.entries, [])
        self.assertFalse(self.window.save_action.isEnabled())

    def test_clear_loaded_playlist_preserves_source_metadata_and_disk(self):
        source = self.root / "existing.json"
        fixture().save(source)
        self.window.load_playlist(source)
        disk_before = source.read_bytes()
        document = self.window.document
        metadata = {key: copy.deepcopy(value) for key, value in document.data.items() if key != "entries"}
        self.map.selected = {0, 1}
        self.map.anchor = 0
        self.map.insertion = self.map.boundary_at(self.position(0))
        self.map.scroll_timer.start()
        self.window.clear_action.trigger()
        self.assertIs(self.window.document, document)
        self.assertEqual(document.source, source)
        self.assertEqual(document.data, dict(metadata, entries=[]))
        self.assertEqual(source.read_bytes(), disk_before)
        self.assertEqual(self.map.entries, [])
        self.assertEqual(self.map.selected, set())
        self.assertIsNone(self.map.anchor)
        self.assertIsNone(self.map.insertion)
        self.assertFalse(self.map.scroll_timer.isActive())
        self.assertTrue(self.window.save_action.isEnabled())
        self.drop_folders([self.song()])
        self.assertEqual(self.names(), ["one"])
        self.assertEqual(self.map.entries[0].number, 1)

    def test_clear_unsaved_playlist_can_add_and_save_again(self):
        song = self.song()
        self.drop_folders([song, self.folder("Category")])
        self.window.clear_action.trigger()
        self.assertIsNone(self.window.document.source)
        self.assertEqual(self.names(), [])
        self.assertEqual(song.read_bytes(), b"original")
        with patch.object(QInputDialog, "getText", return_value=("After Clear", True)):
            self.window.add_category(0)
        destination = self.root / "cleared.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")):
            self.assertTrue(self.window.save_playlist())
        self.assertTrue(self.window.load_playlist(destination))
        self.assertEqual(self.names(), ["After Clear"])

    def test_failed_first_save_does_not_assign_name(self):
        self.drop_folders([self.song()])
        before = copy.deepcopy(self.window.document.data)
        with patch("playlist.os.replace", side_effect=OSError("Cannot save")), \
                patch.object(QMessageBox, "warning"):
            self.assertFalse(self.window.save_to(self.root / "failed.json"))
        self.assertEqual(self.window.document.data, before)
        self.assertIsNone(self.window.document.source)
