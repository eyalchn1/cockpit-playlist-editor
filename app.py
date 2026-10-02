import argparse
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox, QMenu, QInputDialog
from playlist import Playlist, SONG_FILE_FILTER
from view import MapArea
from help_ui import show_help_dialog


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.document = None
        self.overwrite_approved = set()
        self.settings = settings if settings is not None else QSettings(
            str(Path(__file__).resolve().parent / ".user-settings.ini"), QSettings.IniFormat)
        self.setWindowTitle("Cockpit Playlist Editor — Prototype")
        self.resize(1500, 900)
        self.setMinimumSize(500, 320)
        root = QWidget()
        box = QVBoxLayout(root)
        box.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        button = QPushButton("Open Playlist…")
        button.clicked.connect(self.open_dialog)
        header.addWidget(button)
        self.direction_button = QPushButton()
        self.direction_button.setCheckable(True)
        self.direction_button.setFixedWidth(110)
        self.direction_button.clicked.connect(self.toggle_column_direction)
        header.addWidget(self.direction_button)
        header.addStretch()
        brand = QLabel("COCKPIT  /  PLAYLIST EDITOR")
        header.addWidget(brand)
        box.addLayout(header)
        self.name_label = QLabel("מבט על ה־Playlist")
        self.name_label.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        self.name_label.setStyleSheet("font-size: 22px; font-weight: 600;")
        self.name_label.setTextFormat(Qt.PlainText)
        box.addWidget(self.name_label)
        self.count_label = QLabel("עריכה בזיכרון בלבד · עמודות משמאל לימין, שירים מלמעלה למטה")
        self.count_label.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
        box.addWidget(self.count_label)
        self.area = MapArea()
        self.area.map.moveRequested.connect(self.move_songs)
        self.area.map.foldersDropped.connect(self.import_folders)
        self.area.map.pathsDropped.connect(self.import_paths)
        self.area.map.contextRequested.connect(self.show_context_menu)
        box.addWidget(self.area, 1)
        self.setCentralWidget(root)
        action = QAction("Open Playlist…", self)
        action.setShortcut(QKeySequence.Open)
        action.triggered.connect(self.open_dialog)
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(action)
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.triggered.connect(self.save_playlist)
        self.save_as_action = QAction("Save As…", self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.save_as_action.triggered.connect(self.save_as_playlist)
        for item in (self.save_action, self.save_as_action):
            item.setEnabled(False)
            file_menu.addAction(item)
        file_menu.addSeparator()
        self.clear_action = QAction("Clear", self)
        self.clear_action.triggered.connect(self.clear_playlist)
        file_menu.addAction(self.clear_action)
        view_menu = self.menuBar().addMenu("View")
        font_menu = view_menu.addMenu("Font Size")
        for title, shortcuts, callback in (
                ("Increase Font Size", ["Ctrl++", "Ctrl+=", "Ctrl+Shift+="], lambda: self.change_font_size(1)),
                ("Decrease Font Size", ["Ctrl+-"], lambda: self.change_font_size(-1)),
                ("Reset Font Size", ["Ctrl+0"], lambda: self.change_font_size(reset=True))):
            item = QAction(title, self)
            item.setShortcuts([QKeySequence(key) for key in shortcuts])
            item.triggered.connect(callback)
            font_menu.addAction(item)
        self.width_actions = []
        for title, shortcut, callback in (
                ("Increase Column Width", "Ctrl+Right", lambda: self.change_column_width(24)),
                ("Decrease Column Width", "Ctrl+Left", lambda: self.change_column_width(-24)),
                ("Reset Column Width", "Ctrl+Down", lambda: self.change_column_width(reset=True))):
            item = QAction(title, self)
            item.setShortcut(QKeySequence(shortcut))
            item.triggered.connect(callback)
            view_menu.addAction(item)
            self.width_actions.append(item)
        options_menu = self.menuBar().addMenu("Options")
        folder_menu = options_menu.addMenu("Folder Import")
        self.folder_import_group = QActionGroup(self)
        self.folder_import_group.setExclusive(True)
        self.first_level_action = folder_menu.addAction("First Level Only")
        self.include_subfolders_action = folder_menu.addAction("Include Subfolders")
        for item in (self.first_level_action, self.include_subfolders_action):
            item.setCheckable(True)
            self.folder_import_group.addAction(item)
        include = self.settings.value("import/includeSubfolders", False, type=bool)
        (self.include_subfolders_action if include else self.first_level_action).setChecked(True)
        self.folder_import_group.triggered.connect(self.save_folder_import_setting)
        help_menu = self.menuBar().addMenu("Help")
        self.help_dialogs = {}
        for title in ("Help / User Guide", "Keyboard Shortcuts", "About Cockpit Playlist Editor"):
            help_menu.addAction(title, lambda checked=False, topic=title: show_help_dialog(self, topic))
        self.statusBar().showMessage("In-memory editing · Ctrl+Click / Shift+Click · Drag & Drop")
        self.setStyleSheet("QMainWindow, QWidget { background: #101923; color: #e6edf5; } QPushButton { background: #285c68; border: 0; padding: 10px 18px; border-radius: 5px; } QPushButton:hover { background: #367786; } QToolTip { background: #eff5fa; color: #101923; padding: 6px; }")
        for menu in self.menuBar().findChildren(QMenu):
            self.fit_menu_text(menu)
        stored_width = self.settings.value("view/columnWidth", 0, type=int)
        self.area.map.column_width_override = max(120, min(1200, stored_width)) if stored_width else None
        self.area.set_column_direction(self.settings.value("view/rightToLeft", False, type=bool))
        self.update_direction_labels()

    def save_folder_import_setting(self, action):
        self.settings.setValue("import/includeSubfolders", self.include_subfolders_action.isChecked())
        self.settings.sync()

    def update_direction_labels(self):
        rtl = self.area.map.right_to_left
        self.direction_button.setChecked(rtl)
        self.direction_button.setText("← RTL" if rtl else "→ LTR")
        self.direction_button.setToolTip("כיוון עמודות: " + ("מימין לשמאל" if rtl else "משמאל לימין") + "\nלחץ להחלפת הכיוון; סדר ה־Playlist נשאר ללא שינוי")
        self.direction_button.setAccessibleName("החלפת כיוון עמודות")
        direction = "מימין לשמאל" if rtl else "משמאל לימין"
        if self.document is None:
            self.count_label.setText(f"עמודות {direction} · שירים מלמעלה למטה")
        else:
            entries = self.area.map.entries
            categories = sum(e.category for e in entries)
            self.count_label.setText(f"{len(entries) - categories} שירים  ·  {categories} קטגוריות  ·  עמודות {direction} ↓")

    def toggle_column_direction(self):
        self.area.set_column_direction(not self.area.map.right_to_left)
        self.update_direction_labels()
        self.settings.setValue("view/rightToLeft", self.area.map.right_to_left)
        self.settings.sync()

    def open_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Cockpit Playlist",
                    str(self.document.source.parent) if self.document and self.document.source else
                    self.settings.value("files/playlistDirectory", "", type=str), "Playlist JSON (*.json)")
        if filename:
            self.load_playlist(filename)

    def load_playlist(self, filename):
        try:
            document = Playlist.load(filename)
        except (OSError, ValueError, UnicodeError) as error:
            QMessageBox.warning(self, "לא ניתן לפתוח Playlist", str(error))
            return False
        entries = document.display_entries()
        categories = sum(entry.category for entry in entries)
        self.document = document
        self.remember_playlist_directory(document.source)
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.name_label.setText(document.name)
        self.count_label.setText(f"{len(entries) - categories} שירים  ·  {categories} קטגוריות  ·  עמודות משמאל לימין ↓")
        self.area.set_entries(entries)
        self.update_direction_labels()
        self.statusBar().showMessage(str(document.source))
        return True

    def confirm_overwrite(self, destination):
        return QMessageBox.question(self, "אישור דריסת Playlist",
            f"שמירה תחליף את הקובץ הקיים בסדר הנוכחי של השירים והקטגוריות:\n{destination}\n\nהאם לשמור ולדרוס את הקובץ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes

    def remember_playlist_directory(self, filename):
        self.settings.setValue("files/playlistDirectory", str(Path(filename).resolve().parent))
        self.settings.sync()

    def save_to(self, filename, force_confirmation=False):
        if self.document is None:
            return False
        destination = Path(filename).resolve()
        if destination.exists() and (force_confirmation or destination not in self.overwrite_approved):
            if not self.confirm_overwrite(destination):
                return False
        try:
            self.document.save(destination)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "השמירה נכשלה", str(error))
            return False
        self.overwrite_approved.add(destination)
        self.remember_playlist_directory(destination)
        self.name_label.setText(self.document.name)
        self.statusBar().showMessage(f"{destination} · נשמר")
        return True

    def save_playlist(self):
        if self.document is not None:
            if self.document.source is None:
                return self.save_as_playlist()
            return self.save_to(self.document.source)
        return False

    def save_as_playlist(self):
        if self.document is None:
            return False
        initial = str(self.document.source) if self.document.source else str(
            Path(self.settings.value("files/playlistDirectory", "", type=str)) / "Untitled.json")
        filename, _ = QFileDialog.getSaveFileName(self, "Save Playlist As", initial,
            "Playlist JSON (*.json)", options=QFileDialog.DontConfirmOverwrite)
        if not filename:
            return False
        if not Path(filename).suffix:
            filename += ".json"
        return self.save_to(filename, force_confirmation=True)

    def change_font_size(self, delta=0, reset=False):
        self.area.map.set_font_size(10 if reset else self.area.map.font().pointSize() + delta)
        self.area.reflow()

    def change_column_width(self, delta=0, reset=False):
        view = self.area.map
        current = view.column_width_override or view.geometry_plan.column_width
        view.column_width_override = None if reset else max(120, min(1200, current + delta))
        self.area.reflow()
        self.settings.setValue("view/columnWidth", view.column_width_override or 0)
        self.settings.sync()

    def build_context_menu(self, index):
        menu = QMenu(self)
        menu.addAction("Add Song", lambda: self.add_song(index))
        menu.addAction("Add Category", lambda: self.add_category(index))
        menu.addSeparator()
        entries = self.document.data["entries"] if self.document else []
        if index < len(entries) and entries[index].get("is_category", False):
            menu.addAction("Remove Category", lambda: self.remove_category(index))
        else:
            # Capture the selection when the menu opens, before any modal dialogs.
            chosen = sorted(self.area.map.selected) if index in self.area.map.selected else [index]
            action = menu.addAction("Remove Song", lambda: self.remove_songs(chosen))
            action.setEnabled(index < len(entries))
        self.fit_menu_text(menu)
        return menu

    def fit_menu_text(self, menu):
        metrics = menu.fontMetrics()
        labels = [metrics.horizontalAdvance(action.text()) for action in menu.actions()]
        shortcuts = [metrics.horizontalAdvance(action.shortcut().toString(QKeySequence.NativeText))
                     for action in menu.actions()]
        shortcut_width = max(shortcuts, default=0)
        menu.setMinimumWidth(max(labels, default=0) + shortcut_width + 64)
        menu.setStyleSheet(f"QMenu {{ padding: 4px; }} QMenu::item {{ padding: 6px {shortcut_width + 28}px 6px 16px; }}")

    def show_context_menu(self, index, position):
        menu = self.build_context_menu(index)
        try:
            menu.exec(position)
        finally:
            menu.deleteLater()

    def refresh_after_edit(self):
        self.name_label.setText(self.document.name)
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.area.map.reset_selection()
        self.area.map.entries = self.document.display_entries()
        self.area.reflow()
        self.update_direction_labels()
        self.statusBar().showMessage(f"{self.document.source or self.document.name} · שינויים בזיכרון בלבד")

    def add_song(self, index):
        directory = str(self.document.source.parent) if self.document and self.document.source else self.settings.value(
            "files/playlistDirectory", "", type=str)
        filename, _ = QFileDialog.getOpenFileName(self, "Add Song", directory, SONG_FILE_FILTER)
        if not filename:
            return
        if self.document is None:
            self.document = Playlist({"entries": []}, None)
        self.document.insert_entry(index, song_path=str(Path(filename).resolve()))
        self.refresh_after_edit()

    def add_category(self, index):
        name, accepted = QInputDialog.getText(self, "Add Category", "שם הקטגוריה:")
        if not accepted or not name.strip():
            return
        if self.document is None:
            self.document = Playlist({"entries": []}, None)
        self.document.insert_entry(index, category_name=name)
        self.refresh_after_edit()

    def remove_songs(self, indices):
        self.document.remove_entries(indices)
        self.refresh_after_edit()

    def clear_playlist(self):
        if self.document is None:
            return
        self.document.data["entries"].clear()
        self.refresh_after_edit()
        self.area.scroll_to_start()

    def remove_category(self, index):
        name = self.document.data["entries"][index].get("title", "")
        answer = QMessageBox.question(self, "Remove Category",
            f"להסיר את כותרת הקטגוריה '{name}'?\nהשירים שאחריה יישארו ברשימה.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.document.remove_entries([index], categories=True)
            self.refresh_after_edit()

    def move_songs(self, indices, boundary):
        if self.document is None:
            return
        selected = self.document.move_songs(indices, boundary)
        self.area.map.entries = self.document.display_entries()
        self.area.map.selected = set(selected)
        self.area.map.anchor = selected[0] if selected else None
        self.area.reflow()
        self.statusBar().showMessage(f"{self.document.source} · שינויים בזיכרון בלבד")

    def import_folders(self, folders, boundary):
        document = self.document if self.document is not None else Playlist({"entries": []}, None)
        try:
            document.import_folders(folders, boundary,
                                    include_subfolders=self.include_subfolders_action.isChecked())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Folder import failed", str(error))
            return
        self.document = document
        self.name_label.setText(document.name)
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.refresh_after_edit()

    def import_paths(self, paths, boundary):
        document = self.document if self.document is not None else Playlist({"entries": []}, None)
        try:
            document.import_paths(paths, boundary,
                                  include_subfolders=self.include_subfolders_action.isChecked())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Import failed", str(error))
            return
        if self.document is None and not document.data["entries"]:
            return
        self.document = document
        self.refresh_after_edit()


def main():
    parser = argparse.ArgumentParser(description="In-memory Cockpit Playlist editor prototype")
    parser.add_argument("playlist", nargs="?")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    window = MainWindow()
    window.showMaximized()
    if args.playlist:
        window.load_playlist(args.playlist)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
