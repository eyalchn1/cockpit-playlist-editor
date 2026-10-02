import copy
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint, QPointF, QSettings
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from playlist import Playlist
from app import MainWindow
import test_editing


class FolderDropTests(test_editing.EditingWindowTests):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window.settings = QSettings(str(self.root / "settings.ini"), QSettings.IniFormat)

    def tearDown(self):
        super().tearDown()
        self.temp.cleanup()

    def folder(self, name, files=()):
        folder = self.root / name
        folder.mkdir()
        for filename in files:
            (folder / filename).write_bytes(b"unchanged song")
        return folder

    def drop_folders(self, folders, position=None):
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(folder)) for folder in folders])
        position = position if position is not None else (
            self.position(0, 0.1) if self.map.entries else QPoint(50, 5))
        actions = Qt.CopyAction | Qt.MoveAction
        for event in (
                QDragEnterEvent(position, actions, mime, Qt.LeftButton, Qt.NoModifier),
                QDragMoveEvent(position, actions, mime, Qt.LeftButton, Qt.NoModifier),
                QDropEvent(QPointF(position), actions, mime, Qt.LeftButton, Qt.NoModifier)):
            QApplication.sendEvent(self.map, event)
            self.assertTrue(event.isAccepted())
            self.assertEqual(event.dropAction(), Qt.CopyAction)
        self.assertIsNone(self.map.insertion)
        self.assertFalse(self.map.scroll_timer.isActive())

    def names(self):
        return [entry.name for entry in self.map.entries]

    def recursive_folder(self):
        self.window.include_subfolders_action.trigger()
        return self.folder("Root", ["root.mid"])

    def child(self, parent, name, files=()):
        folder = parent / name
        folder.mkdir()
        for filename in files:
            (folder / filename).write_bytes(b"unchanged song")
        return folder

    def test_first_level_default_and_explicit_selection(self):
        self.assertTrue(self.window.first_level_action.isChecked())
        self.assertFalse(self.window.include_subfolders_action.isChecked())
        self.window.include_subfolders_action.trigger()
        self.window.first_level_action.trigger()
        folder = self.folder("Root", ["direct.mid"])
        self.child(folder, "Child", ["nested.mid"])
        self.drop_folders([folder])
        self.assertEqual(self.names()[:3], ["Root", "direct", "A"])

    def test_recursive_one_level_with_natural_folder_and_song_order(self):
        folder = self.recursive_folder()
        self.child(folder, "album 10", ["Song 10.mid", "song 2.WRK", "Song 1.MIDI"])
        self.child(folder, "Album 2", ["two.mid"])
        self.child(folder, "ALBUM 1", ["one.mid"])
        self.drop_folders([folder])
        self.assertEqual(self.names()[:10], ["Root", "root", "ALBUM 1", "one", "Album 2", "two",
                                              "album 10", "Song 1", "song 2", "Song 10"])

    def test_recursive_multiple_depths_preorder(self):
        folder = self.recursive_folder()
        child = self.child(folder, "Child", ["child.mid"])
        grandchild = self.child(child, "Grandchild", ["grand.mid"])
        self.child(grandchild, "Great grandchild", ["great.mid"])
        self.child(folder, "Sibling", ["sibling.mid"])
        self.drop_folders([folder])
        self.assertEqual(self.names()[:10], ["Root", "root", "Child", "child", "Grandchild", "grand",
                                              "Great grandchild", "great", "Sibling", "sibling"])

    def test_recursive_parent_with_only_subfolders(self):
        self.window.include_subfolders_action.trigger()
        folder = self.folder("Parent")
        self.child(folder, "Child", ["song.mid"])
        self.drop_folders([folder])
        self.assertEqual(self.names()[:4], ["Parent", "Child", "song", "A"])
        self.assertIsNone(self.map.entries[0].number)
        self.assertIsNone(self.map.entries[1].number)

    def test_recursive_empty_subfolder(self):
        folder = self.recursive_folder()
        self.child(folder, "Empty")
        self.drop_folders([folder])
        self.assertEqual(self.names()[:4], ["Root", "root", "Empty", "A"])
        self.assertTrue(self.map.entries[2].category)

    def test_recursive_mixed_file_types_and_source_unchanged(self):
        folder = self.recursive_folder()
        self.child(folder, "Mixed", ["one.WRK", "two.mId", "three.MIDI", "ignored.mp3", "notes.txt"])
        before = {path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}
        self.drop_folders([folder])
        self.assertEqual(self.names()[:6], ["Root", "root", "Mixed", "one", "three", "two"])
        self.assertEqual({path: path.read_bytes() for path in folder.rglob("*") if path.is_file()}, before)

    def test_recursive_multiple_roots_drop_middle_rtl_and_save(self):
        first = self.recursive_folder()
        self.child(first, "Child", ["child.mid"])
        second = self.folder("Second", ["second.mid"])
        self.child(second, "Empty")
        for rtl in (False, True):
            self.window.document = test_editing.fixture()
            self.window.refresh_after_edit()
            self.window.area.set_column_direction(rtl)
            self.drop_folders([first, second], self.position(3, 0.1))
            self.assertEqual(self.names(), ["A", "B", "Festival", "Root", "root", "Child", "child",
                                            "Second", "second", "Empty", "C", "D", "E"])
            self.assertEqual([e.number for e in self.map.entries if not e.category], list(range(1, 9)))
            expected = copy.deepcopy(self.window.document.data)
            destination = self.root / f"recursive-{rtl}.json"
            self.assertFalse(destination.exists())
            self.assertTrue(self.window.save_to(destination))
            self.assertTrue(self.window.load_playlist(destination))
            self.assertEqual(self.window.document.data, expected)

    def test_recursive_drop_into_empty_playlist_and_new_document(self):
        folder = self.recursive_folder()
        self.child(folder, "Child", ["child.mid"])
        for new in (False, True):
            if new:
                self.window.document = None
                self.window.area.set_entries([])
            else:
                self.window.document.data["entries"].clear()
                self.window.refresh_after_edit()
            self.drop_folders([folder])
            self.assertEqual(self.names(), ["Root", "root", "Child", "child"])

    def test_folder_import_settings_exclusive_and_persist_between_windows(self):
        preferences = str(self.root / "settings.ini")
        folder = self.folder("Root", ["direct.mid"])
        self.child(folder, "Child", ["nested.mid"])
        for include in (True, False):
            action = self.window.include_subfolders_action if include else self.window.first_level_action
            action.trigger()
            action.trigger()  # Clicking the selected exclusive action keeps it checked.
            self.assertEqual(self.window.include_subfolders_action.isChecked(), include)
            self.assertEqual(self.window.first_level_action.isChecked(), not include)
            reopened = MainWindow(settings=QSettings(preferences, QSettings.IniFormat))
            try:
                self.assertEqual(reopened.include_subfolders_action.isChecked(), include)
                self.assertEqual(reopened.first_level_action.isChecked(), not include)
                reopened.import_folders([folder], 0)
                self.assertEqual([e.name for e in reopened.area.map.entries],
                                 ["Root", "direct", "Child", "nested"] if include else ["Root", "direct"])
            finally:
                reopened.close()

    def test_recursive_unreadable_subfolder_leaves_playlist_unchanged(self):
        folder = self.recursive_folder()
        child = self.child(folder, "Child")
        original = copy.deepcopy(self.window.document.data)
        real_iterdir = Path.iterdir

        def iterdir(path):
            if path == child:
                raise PermissionError("Access denied")
            return real_iterdir(path)

        with patch.object(Path, "iterdir", iterdir), patch.object(QMessageBox, "warning") as warning:
            self.drop_folders([folder])
        warning.assert_called_once()
        self.assertEqual(self.window.document.data, original)

    def test_recursive_ancestor_directory_link_does_not_loop(self):
        folder = self.recursive_folder()
        link = self.child(folder, "Back to root")
        real_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            # Model the resolved target of a Windows junction without requiring
            # developer mode or privileges to create real directory links.
            return folder if path == link else real_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve):
            self.drop_folders([folder])
        self.assertEqual(self.names()[:3], ["Root", "root", "A"])

    def test_single_folder_natural_order_and_entry_compatibility(self):
        folder = self.folder("Sixties", ["Song 10.MID", "song 2.wrk", "Song 1.mIdI"])
        self.drop_folders([folder])
        self.assertEqual(self.names()[:4], ["Sixties", "Song 1", "song 2", "Song 10"])
        expected = Playlist({"entries": []}, None)
        expected.insert_entry(0, category_name="Sixties")
        for name in ["Song 1.mIdI", "song 2.wrk", "Song 10.MID"]:
            expected.insert_entry(len(expected.data["entries"]), song_path=str(folder / name))
        self.assertEqual(self.window.document.data["entries"][:4], expected.data["entries"])
        for path in folder.iterdir():
            self.assertEqual(path.read_bytes(), b"unchanged song")

    def test_multiple_folders_at_middle_in_both_directions(self):
        folders = [self.folder("Sixties", ["A.mid"]), self.folder("Seventies", ["B.wrk"]),
                   self.folder("Beatles", ["C.midi"])]
        for rtl in (False, True):
            self.window.document = test_editing.fixture()
            self.window.refresh_after_edit()
            self.window.area.set_column_direction(rtl)
            original = copy.deepcopy(self.window.document.data)
            self.drop_folders(folders, self.position(3, 0.1))
            self.assertEqual(self.names(), ["A", "B", "Festival", "Sixties", "A", "Seventies",
                                            "B", "Beatles", "C", "C", "D", "E"])
            self.assertEqual(self.window.document.data["entries"][:3], original["entries"][:3])
            self.assertEqual(self.window.document.data["entries"][9:], original["entries"][3:])
            self.assertEqual([e.number for e in self.map.entries if not e.category], list(range(1, 9)))
            self.assertTrue(all(e.number is None for e in self.map.entries if e.category))

    def test_empty_folder_still_creates_category(self):
        self.drop_folders([self.folder("Empty")])
        self.assertEqual(self.names()[0], "Empty")
        self.assertTrue(self.map.entries[0].category)

    def test_unsupported_files_are_skipped(self):
        self.drop_folders([self.folder("Mixed", ["yes.mid", "yes2.WRK", "no.mp3", "no.txt"])])
        self.assertEqual(self.names()[:4], ["Mixed", "yes2", "yes", "A"])

    def test_subfolders_are_not_scanned(self):
        folder = self.folder("Parent", ["direct.mid"])
        subfolder = folder / "Child.mid"
        subfolder.mkdir()
        (subfolder / "nested.wrk").write_bytes(b"nested")
        self.drop_folders([folder])
        self.assertEqual(self.names()[:3], ["Parent", "direct", "A"])
        self.assertEqual((subfolder / "nested.wrk").read_bytes(), b"nested")

    def test_drop_into_empty_loaded_playlist(self):
        self.window.document.data["entries"].clear()
        self.window.refresh_after_edit()
        self.drop_folders([self.folder("First", ["one.mid"]), self.folder("Second")])
        self.assertEqual(self.names(), ["First", "one", "Second"])

    def test_drop_without_document_and_save_reload(self):
        self.window.document = None
        self.window.area.set_entries([])
        self.drop_folders([self.folder("New", ["one.mid"])])
        self.assertIsNone(self.window.document.source)
        self.assertTrue(self.window.save_action.isEnabled())
        self.assertTrue(self.window.save_as_action.isEnabled())
        self.assertEqual(self.names(), ["New", "one"])
        expected = copy.deepcopy(self.window.document.data)
        destination = self.root / "saved.json"
        self.assertFalse(destination.exists())
        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")):
            self.assertFalse(self.window.save_playlist())
        self.assertIsNone(self.window.document.source)
        self.assertEqual(self.window.document.data, expected)
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")):
            self.assertTrue(self.window.save_playlist())
        expected["name"] = "saved"
        self.assertEqual(Playlist.load(destination).data, expected)
        self.assertTrue(self.window.load_playlist(destination))
        self.assertEqual(self.names(), ["New", "one"])

    def test_existing_source_not_saved_and_imported_songs_can_move(self):
        source = self.root / "original.json"
        self.window.document.save(source)
        before = source.read_bytes()
        self.drop_folders([self.folder("New", ["one.mid", "two.mid"])])
        self.assertEqual(source.read_bytes(), before)
        self.click(1)
        self.click(2, Qt.ControlModifier)
        self.drag_with_qt_events(1, self.position(len(self.map.entries) - 1, 0.9))
        self.assertEqual(self.names()[-2:], ["one", "two"])
        self.window.change_font_size(1)
        self.window.change_column_width(24)
        self.assertEqual(source.read_bytes(), before)
        destination = self.root / "edited.json"
        self.assertTrue(self.window.save_to(destination))
        self.assertTrue(self.window.load_playlist(destination))
        self.assertEqual(self.names()[-2:], ["one", "two"])

    def test_unreadable_folder_import_is_atomic(self):
        original = copy.deepcopy(self.window.document.data)
        folder = self.folder("Readable", ["one.mid"])
        missing = self.root / "Missing"
        with patch.object(QMessageBox, "warning") as warning:
            self.window.import_folders([folder, missing], 2)
        warning.assert_called_once()
        self.assertEqual(self.window.document.data, original)
        with patch.object(Path, "iterdir", side_effect=PermissionError("Access denied")), \
                patch.object(QMessageBox, "warning") as warning:
            self.window.import_folders([folder], 2)
        warning.assert_called_once()
        self.assertEqual(self.window.document.data, original)

    def test_file_and_remote_url_drags_are_rejected(self):
        folder = self.folder("Folder", ["one.mid"])
        unsupported = folder / "notes.txt"
        unsupported.write_text("notes")
        for urls in ([QUrl.fromLocalFile(str(unsupported))],
                     [QUrl("https://example.com/folder")]):
            mime = QMimeData()
            mime.setUrls(urls)
            event = QDragEnterEvent(QPoint(50, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
            QApplication.sendEvent(self.map, event)
            self.assertFalse(event.isAccepted())
