import unittest
from math import ceil

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from layout import calculate_layout
from playlist import Playlist
from view import MapArea


class VerticalLayoutTests(unittest.TestCase):
    def test_vertical_fill_is_independent_of_available_width(self):
        for width in (180, 600, 3000):
            with self.subTest(width=width):
                plan = calculate_layout(85, width, 35 * 28 + 10, 28, 190)
                self.assertEqual((plan.rows, plan.columns), (35, 3))
                self.assertEqual([min(plan.rows, 85 - column * plan.rows)
                                  for column in range(plan.columns)], [35, 35, 15])

    def test_short_empty_exact_and_overflow_playlists(self):
        for count, columns in ((0, 1), (3, 1), (35, 1), (70, 2), (71, 3)):
            plan = calculate_layout(count, 2000, 980, 28, 190)
            self.assertEqual((plan.rows, plan.columns), (35, columns))

    def test_fixed_width_and_small_viewport(self):
        plan = calculate_layout(85, 500, 980, 28, 190, fixed_width=240)
        self.assertEqual((plan.rows, plan.columns, plan.column_width, plan.content_width),
                         (35, 3, 240, 720))
        for height in (0, 10, 28):
            self.assertEqual(calculate_layout(3, 500, height, 28, 190).rows, 1)

    def test_preferred_width_does_not_depend_on_column_count_or_viewport(self):
        for width in (180, 600, 3000):
            for count, columns in ((0, 1), (3, 1), (35, 1), (70, 2), (85, 3), (350, 10)):
                with self.subTest(width=width, count=count):
                    plan = calculate_layout(count, width, 980, 28, 190)
                    self.assertEqual((plan.rows, plan.columns, plan.column_width, plan.content_width),
                                     (35, columns, 190, columns * 190))


class ViewportFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.area = MapArea()
        self.document = Playlist({"entries": [
            {"path": f"{i}.mid", "title": str(i), "is_category": i % 11 == 0,
             "hierarchy_depth": i % 3} for i in range(85)]}, None)
        self.entries = self.document.display_entries()
        self.area.set_entries(self.entries)
        self.area.resize(2000, 650)
        self.area.show()
        self.app.processEvents()

    def tearDown(self):
        self.area.close()
        self.area.deleteLater()
        self.app.processEvents()

    def assert_flow(self):
        view = self.area.map
        plan = view.geometry_plan
        self.assertEqual(plan.rows, max(1, self.area.viewport().height() // view.row_height))
        self.assertEqual(plan.columns, ceil(len(self.entries) / plan.rows))
        self.assertEqual(view.entries, self.entries)
        for index in range(len(self.entries)):
            column, row = divmod(index, plan.rows)
            point = QPoint(view.visual_column(column) * plan.column_width + 10,
                           row * view.row_height + view.row_height // 2)
            self.assertEqual(view.index_at(point), index)

    def test_resize_font_and_viewport_space_recalculate_capacity(self):
        self.area.map.selected = {1, 2}
        self.area.map.anchor = 1
        self.assert_flow()
        initial_rows = self.area.map.geometry_plan.rows
        self.area.resize(2000, 400)
        self.app.processEvents()
        self.assert_flow()
        self.assertLess(self.area.map.geometry_plan.rows, initial_rows)
        before_font = self.area.map.geometry_plan.rows
        font = QFont(self.area.map.font())
        font.setPointSize(24)
        self.area.map.setFont(font)
        self.app.processEvents()
        self.assert_flow()
        self.assertLess(self.area.map.geometry_plan.rows, before_font)
        before_margins = self.area.map.geometry_plan.rows
        self.area.setViewportMargins(0, 0, 0, 100)
        self.app.processEvents()
        self.assert_flow()
        self.assertLess(self.area.map.geometry_plan.rows, before_margins)
        self.assertEqual(self.area.map.selected, {1, 2})
        self.assertEqual(self.area.map.anchor, 1)

    def test_ltr_rtl_fixed_width_and_horizontal_scroll(self):
        self.area.map.column_width_override = 240
        for rtl in (False, True):
            self.area.set_column_direction(rtl)
            self.area.resize(500, 400)
            self.app.processEvents()
            self.area.scroll_to_start()
            self.assert_flow()
            plan = self.area.map.geometry_plan
            self.assertEqual(plan.column_width, 240)
            self.assertGreater(plan.content_width, self.area.viewport().width())
            bar = self.area.horizontalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            self.assertEqual(bar.value(), bar.maximum() if rtl else 0)
            rows = plan.rows
            self.area.resize(2000, 400)
            self.app.processEvents()
            self.assert_flow()
            self.assertEqual(self.area.map.geometry_plan.rows, rows)

    def test_preferred_width_empty_space_direction_and_overflow(self):
        view = self.area.map
        preferred = view.geometry_plan.column_width
        row_height = view.row_height
        rows = view.geometry_plan.rows
        for rtl in (False, True):
            self.area.set_column_direction(rtl)
            for columns in (1, 2, 3):
                with self.subTest(rtl=rtl, columns=columns):
                    entries = self.entries[:(columns - 1) * rows + 3]
                    self.area.set_entries(entries)
                    self.app.processEvents()
                    plan = view.geometry_plan
                    self.assertEqual((plan.rows, plan.columns, plan.column_width),
                                     (rows, columns, preferred))
                    self.assertEqual(view.row_height, row_height)
                    self.assertEqual(view.width(), columns * preferred)
                    self.assertLess(view.width(), self.area.viewport().width())
                    self.assertEqual(self.area.horizontalScrollBar().maximum(), 0)
                    origin = view.mapTo(self.area.viewport(), QPoint(0, 0))
                    self.assertEqual(origin.x(), self.area.viewport().width() - view.width() if rtl else 0)
                    first = QPoint(view.visual_column(0) * preferred + 10, row_height // 2)
                    self.assertEqual(view.index_at(first), 0)
                    blank_x = origin.x() - 1 if rtl else origin.x() + view.width()
                    blank = view.mapFrom(self.area.viewport(), QPoint(blank_x, row_height // 2))
                    self.assertIsNone(view.index_at(blank))
            self.area.resize(preferred * 2 - 10, 650)
            self.app.processEvents()
            self.area.scroll_to_start()
            plan = view.geometry_plan
            self.assertEqual((plan.rows, plan.column_width), (rows, preferred))
            bar = self.area.horizontalScrollBar()
            self.assertGreater(bar.maximum(), 0)
            self.assertEqual(bar.value(), bar.maximum() if rtl else 0)
            self.area.resize(2000, 650)
            self.app.processEvents()
