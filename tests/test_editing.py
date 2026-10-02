import copy
import hashlib
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QPoint, QPointF, QMimeData, QSettings
from PySide6.QtGui import QDrag, QDragEnterEvent, QDragMoveEvent, QDropEvent, QDragLeaveEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import MainWindow
from playlist import Playlist


def fixture():
    return Playlist({"name": "Test", "unknown": {"nested": [1, 2]}, "entries": [
        {"path": f"..\\music\\{name}.WRK", "title": name, "is_category": category,
         "mixer_levels": [i, 127], "future_field": {"index": i}}
        for i, (name, category) in enumerate([
            ("A", False), ("B", False), ("Festival", True),
            ("C", False), ("D", False), ("E", False)])]}, Path("test.json"))


class ReorderTests(unittest.TestCase):
    def assert_order(self, document, expected):
        self.assertEqual([e["title"] for e in document.data["entries"]], expected.split())

    def test_single_forward_and_backward(self):
        doc = fixture()
        self.assertEqual(doc.move_songs([0], 5), [4])
        self.assert_order(doc, "B Festival C D A E")
        self.assertEqual(doc.move_songs([4], 0), [0])
        self.assert_order(doc, "A B Festival C D E")

    def test_group_order_and_all_fields(self):
        doc = fixture()
        original = copy.deepcopy(doc.data)
        objects = {e["title"]: e for e in doc.data["entries"]}
        self.assertEqual(doc.move_songs([4, 0, 3], 6), [3, 4, 5])
        self.assert_order(doc, "B Festival E A C D")
        for entry in doc.data["entries"]:
            self.assertIs(entry, objects[entry["title"]])
            self.assertEqual(entry, next(e for e in original["entries"] if e["title"] == entry["title"]))
        self.assertEqual(doc.data["unknown"], original["unknown"])

    def test_before_and_after_category_and_numbering(self):
        doc = fixture()
        doc.move_songs([5], 2)
        self.assert_order(doc, "A B E Festival C D")
        doc.move_songs([0], 4)
        self.assert_order(doc, "B E Festival A C D")
        self.assertEqual([e.number for e in doc.display_entries()], [1, 2, None, 3, 4, 5])

    def test_boundaries_and_noop(self):
        for boundary in (1, 2, 3):
            doc = fixture()
            # A contiguous group on either side of/inside its own range is unchanged.
            doc.move_songs([3, 4], boundary + 2)
            self.assert_order(doc, "A B Festival C D E")
        doc = fixture()
        doc.move_songs([5], 0)
        self.assert_order(doc, "E A B Festival C D")
        doc.move_songs([0], 6)
        self.assert_order(doc, "A B Festival C D E")

    def test_invalid_moves_are_atomic(self):
        doc = fixture()
        original = copy.deepcopy(doc.data)
        for indices, boundary in [([2], 0), ([-1], 0), ([6], 0), ([0], 7), ([0], -1)]:
            with self.assertRaises(ValueError):
                doc.move_songs(indices, boundary)
            self.assertEqual(doc.data, original)


class LocalEnter(QDragEnterEvent):
    def source(self):
        return self.local_source


class LocalMove(QDragMoveEvent):
    def source(self):
        return self.local_source


class LocalDrop(QDropEvent):
    def source(self):
        return self.local_source


class EditingWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings_folder = tempfile.TemporaryDirectory()
        self.window = MainWindow(settings=QSettings(
            str(Path(self.settings_folder.name) / "settings.ini"), QSettings.IniFormat))
        self.window.document = fixture()
        self.window.area.set_entries(self.window.document.display_entries())
        self.window.resize(1100, 600)
        self.window.show()
        self.app.processEvents()
        self.map = self.window.area.map

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.settings_folder.cleanup()

    def position(self, index, fraction=0.5):
        plan = self.map.geometry_plan
        column, row = divmod(index, plan.rows)
        column = self.map.visual_column(column)
        return QPoint(column * plan.column_width + 60, int((row + fraction) * self.map.row_height))

    def click(self, index, modifier=Qt.NoModifier):
        QTest.mouseClick(self.map, Qt.LeftButton, modifier, self.position(index))

    def test_click_ctrl_shift_and_category(self):
        self.click(0)
        self.assertEqual(self.map.selected, {0})
        self.click(4, Qt.ControlModifier)
        self.assertEqual(self.map.selected, {0, 4})
        self.click(4, Qt.ControlModifier)
        self.assertEqual(self.map.selected, {0})
        self.click(0)
        self.click(5, Qt.ShiftModifier)
        self.assertEqual(self.map.selected, {0, 1, 3, 4, 5})
        self.click(2)
        self.assertEqual(self.map.selected, {0, 1, 3, 4, 5})
        self.click(3)
        self.assertEqual(self.map.selected, {3})
        self.click(1)
        self.assertEqual(self.map.selected, {1})

    def test_boundary_hit_testing(self):
        for index in range(len(self.map.entries)):
            self.assertEqual(self.map.boundary_at(self.position(index, 0.1))[0], index)
            self.assertEqual(self.map.boundary_at(self.position(index, 0.9))[0], index + 1)
        self.assertEqual(self.map.boundary_at(self.position(0, 0))[0], 0)

    def deliver_drop(self, source, mime, destination, screenshot=False):
        enter = LocalEnter(destination, Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        enter.local_source = source
        QApplication.sendEvent(self.map, enter)
        self.assertTrue(enter.isAccepted())
        move = LocalMove(destination, Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        move.local_source = source
        QApplication.sendEvent(self.map, move)
        self.assertTrue(move.isAccepted())
        self.assertIsNotNone(self.map.insertion)
        if screenshot:
            Path("test-output").mkdir(exist_ok=True)
            self.window.grab().save("test-output/drag-insertion.png")
        drop = LocalDrop(QPointF(destination), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        drop.local_source = source
        QApplication.sendEvent(self.map, drop)
        self.assertTrue(drop.isAccepted())
        self.assertIsNone(self.map.insertion)

    def drag_with_qt_events(self, start, destination, screenshot=False):
        test = self

        class EventDrivenDrag:
            def __init__(self, source):
                self.source = source

            def setMimeData(self, mime):
                self.mime = mime

            def exec(self, action):
                test.deliver_drop(self.source, self.mime, destination, screenshot)
                return Qt.MoveAction

        QTest.mousePress(self.map, Qt.LeftButton, Qt.NoModifier, self.position(start))
        with patch("view.QDrag", EventDrivenDrag):
            QTest.mouseMove(self.map, self.position(start) + QPoint(25, 0))
        QTest.mouseRelease(self.map, Qt.LeftButton, Qt.NoModifier, destination)

    def test_group_drag_across_columns_and_category(self):
        self.click(0)
        self.click(1, Qt.ControlModifier)
        self.drag_with_qt_events(0, self.position(4, 0.9))
        self.assertEqual([e.name for e in self.map.entries], ["Festival", "C", "D", "A", "B", "E"])
        self.assertEqual(self.map.selected, {3, 4})
        self.assertEqual([e.number for e in self.map.entries], [None, 1, 2, 3, 4, 5])

    def test_single_drag_after_category(self):
        self.drag_with_qt_events(0, self.position(2, 0.9))
        self.assertEqual([e.name for e in self.map.entries], ["B", "Festival", "A", "C", "D", "E"])

    def test_drag_start_and_cancel(self):
        original = copy.deepcopy(self.window.document.data)
        self.click(0)
        self.click(1, Qt.ControlModifier)
        QTest.mousePress(self.map, Qt.LeftButton, Qt.NoModifier, self.position(0))
        observed = []

        def cancel(*args):
            observed.append(self.map.drag_indices)
            return Qt.IgnoreAction

        # Native Windows drag loops need physical input; simulate cancellation at
        # the exec boundary, while retaining the real QDrag and QMimeData objects.
        with patch.object(QDrag, "exec", cancel):
            QTest.mouseMove(self.map, self.position(0) + QPoint(25, 0))
        QTest.mouseRelease(self.map, Qt.LeftButton, Qt.NoModifier, self.position(0))
        self.assertEqual(observed, [[0, 1]])
        self.assertEqual(self.window.document.data, original)
        self.assertEqual(self.map.selected, {0, 1})
        self.assertIsNone(self.map.insertion)

    def test_external_drag_rejected_and_leave_clears_marker(self):
        original = copy.deepcopy(self.window.document.data)
        mime = QMimeData()
        mime.setData(self.map.drag_format, b"internal")
        event = LocalEnter(self.position(3), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
        event.local_source = None
        QApplication.sendEvent(self.map, event)
        self.assertFalse(event.isAccepted())
        self.map.insertion = self.map.boundary_at(self.position(3))
        self.map.scroll_timer.start()
        self.map.dragLeaveEvent(QDragLeaveEvent())
        self.assertIsNone(self.map.insertion)
        self.assertFalse(self.map.scroll_timer.isActive())
        self.assertEqual(self.window.document.data, original)

    def test_column_end_and_append_boundaries(self):
        self.window.resize(800, 350)
        self.window.document = Playlist({"entries": [
            {"path": f"{i}.mid", "is_category": False} for i in range(80)]}, Path("test.json"))
        self.window.area.set_entries(self.window.document.display_entries())
        self.app.processEvents()
        plan = self.map.geometry_plan
        last_in_column = plan.rows - 1
        end = self.map.boundary_at(self.position(last_in_column, 0.9))
        start = self.map.boundary_at(self.position(plan.rows, 0.1))
        self.assertEqual(end, (plan.rows, self.map.visual_column(0), plan.rows))
        self.assertEqual(start, (plan.rows, self.map.visual_column(1), 0))
        self.assertEqual(self.map.boundary_at(self.position(79, 0.9))[0], 80)

    @unittest.skipUnless(os.environ.get("COCKPIT_TEST_PLAYLIST"), "Set COCKPIT_TEST_PLAYLIST")
    def test_real_playlist_long_distance_drop_and_reload(self):
        source = Path(os.environ["COCKPIT_TEST_PLAYLIST"])
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        self.window.load_playlist(source)
        original = copy.deepcopy(self.window.document.data)
        self.window.resize(1920, 1080)
        self.app.processEvents()
        geometry = self.map.geometry_plan
        songs = [e.index for e in self.map.entries if not e.category]
        selected = [songs[11], songs[13], songs[15]]
        moving = [original["entries"][i] for i in selected]
        self.click(selected[0])
        for index in selected[1:]:
            self.click(index, Qt.ControlModifier)
        target = songs[139]
        self.drag_with_qt_events(selected[1], self.position(target, 0.9), screenshot=True)
        self.assertEqual(self.map.geometry_plan, geometry)
        new_indices = sorted(self.map.selected)
        self.assertEqual([self.window.document.data["entries"][i] for i in new_indices], moving)
        self.assertEqual(self.map.entries[new_indices[0]].number, 138)
        self.assertEqual(sorted(self.window.document.data["entries"], key=lambda e: str(e)), sorted(original["entries"], key=lambda e: str(e)))
        self.window.grab().save("test-output/after-drop.png")
        with tempfile.TemporaryDirectory() as folder:
            target_file = Path(folder) / "dragged.json"
            expected = copy.deepcopy(self.window.document.data)
            self.assertTrue(self.window.save_to(target_file))
            self.assertEqual(Playlist.load(target_file).data, expected)
            self.window.load_playlist(target_file)
            self.assertEqual(self.window.document.data, expected)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.window.load_playlist(source)
        self.assertEqual(self.window.document.data, original)
        self.assertEqual(self.map.selected, set())
