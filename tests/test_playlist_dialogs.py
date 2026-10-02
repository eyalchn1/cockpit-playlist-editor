import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app import MainWindow, main
from playlist import Playlist


class PlaylistDialogDirectoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings_file = self.root / "settings.ini"
        self.window = MainWindow(settings=QSettings(str(self.settings_file), QSettings.IniFormat))
        self.documents = self.root / "Documents"
        self.documents.mkdir()
        self.standard_paths = patch("app.QStandardPaths.writableLocation", return_value=str(self.documents))
        self.location = self.standard_paths.start()

    def tearDown(self):
        self.standard_paths.stop()
        self.window.close()
        self.temp.cleanup()

    def playlist(self, directory, name="playlist.json"):
        directory.mkdir(exist_ok=True)
        path = directory / name
        Playlist({"entries": []}, None).save(path)
        return path

    def assert_dialog_directory(self, directory, name="Untitled.json"):
        with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")) as picker:
            self.window.open_dialog()
            self.assertEqual(picker.call_args.args[2], str(directory))
        if self.window.document is None:
            self.window.document = Playlist({"entries": []}, None)
        with patch.object(QFileDialog, "getSaveFileName", return_value=("", "")) as picker:
            self.assertFalse(self.window.save_as_playlist())
            self.assertEqual(picker.call_args.args[2], str(directory / name))

    def test_first_run_documents_fallback(self):
        self.assert_dialog_directory(self.documents)
        self.location.assert_called_with(QStandardPaths.DocumentsLocation)
        self.assertFalse(self.window.settings.contains("files/playlistDirectory"))

    def test_invalid_or_missing_directory_falls_back_even_with_loaded_source(self):
        source = self.playlist(self.root / "source")
        self.assertTrue(self.window.load_playlist(source))
        file_path = self.root / "not-a-directory"
        file_path.write_text("file")
        deleted = self.root / "deleted"
        deleted.mkdir()
        deleted.rmdir()
        for value in ("", str(self.root / "missing"), str(deleted), str(file_path), "."):
            with self.subTest(value=value):
                self.window.settings.setValue("files/playlistDirectory", value)
                self.assert_dialog_directory(self.documents, source.name)

    def test_open_remembers_directory_across_sessions(self):
        for directory in (self.root / "first", self.root / "second"):
            source = self.playlist(directory)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "")):
                self.window.open_dialog()
            self.assertEqual(self.window.settings.value("files/playlistDirectory"), str(directory))
            self.assert_dialog_directory(directory, source.name)
        reopened = MainWindow(settings=QSettings(str(self.settings_file), QSettings.IniFormat))
        try:
            self.assertEqual(reopened.playlist_dialog_directory(), directory)
        finally:
            reopened.close()

    def test_save_as_and_save_remember_successful_directory(self):
        source = self.playlist(self.root / "source")
        self.window.load_playlist(source)
        destination_dir = self.root / "saved"
        destination_dir.mkdir()
        destination = destination_dir / "copy.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")):
            self.assertTrue(self.window.save_as_playlist())
        self.assertEqual(self.window.settings.value("files/playlistDirectory"), str(destination_dir))
        self.assert_dialog_directory(destination_dir, destination.name)
        self.window.settings.setValue("files/playlistDirectory", str(self.documents))
        self.assertTrue(self.window.save_playlist())
        self.assertEqual(self.window.settings.value("files/playlistDirectory"), str(destination_dir))
        persisted = QSettings(str(self.settings_file), QSettings.IniFormat)
        self.assertEqual(persisted.value("files/playlistDirectory"), str(destination_dir))

    def test_cockpit_command_line_path_remembers_directory(self):
        source = self.playlist(self.root / "Cockpit playlists")
        application = Mock()
        application.exec.return_value = 0
        with patch.object(sys, "argv", ["CPE", str(source)]), \
                patch("app.QApplication", return_value=application), \
                patch("app.MainWindow", return_value=self.window):
            self.assertEqual(main(), 0)
        self.assertEqual(self.window.document.source, source)
        self.assertEqual(self.window.settings.value("files/playlistDirectory"), str(source.parent))
        self.assert_dialog_directory(source.parent, source.name)

    def test_cancel_failed_open_and_failed_save_preserve_directory(self):
        source = self.playlist(self.root / "source")
        self.window.load_playlist(source)
        with patch.object(QMessageBox, "warning"):
            self.assertFalse(self.window.load_playlist(self.root / "missing.json"))
            with patch.object(self.window.document, "save", side_effect=OSError("disk error")):
                self.assertFalse(self.window.save_to(self.root / "failed.json"))
        self.assert_dialog_directory(source.parent, source.name)
        self.assertEqual(self.window.settings.value("files/playlistDirectory"), str(source.parent))
