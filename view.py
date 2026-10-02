from PySide6.QtCore import Qt, QRect, QSize, QEvent, Signal, QMimeData, QTimer
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QDrag, QCursor
from PySide6.QtWidgets import QWidget, QScrollArea, QToolTip, QApplication
from layout import calculate_layout
from pathlib import Path
from playlist import is_supported_song


class PlaylistMap(QWidget):
    moveRequested = Signal(object, int)
    foldersDropped = Signal(object, int)
    pathsDropped = Signal(object, int)
    contextRequested = Signal(int, object)
    drag_format = "application/x-cockpit-playlist-songs"

    def __init__(self):
        super().__init__()
        self.entries = []
        self.geometry_plan = None
        self.right_to_left = False
        self.column_width_override = None
        self.setFont(QFont("Segoe UI", 10))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.selected = set()
        self.anchor = None
        self.press_position = None
        self.pending_single = None
        self.drag_indices = None
        self.insertion = None
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setInterval(50)
        self.scroll_timer.timeout.connect(self.scroll_during_drag)
        self.scroll_direction = 0

    def reset_selection(self):
        self.selected.clear()
        self.anchor = None
        self.press_position = None
        self.pending_single = None
        self.clear_drag_feedback()
        self.update()

    def contextMenuEvent(self, event):
        index = self.index_at(event.pos())
        if index is not None:
            if not self.entries[index].category and index not in self.selected:
                self.selected = {index}
                self.anchor = index
                self.update()
            self.contextRequested.emit(index, event.globalPos())
            event.accept()
        elif not self.entries:
            self.contextRequested.emit(0, event.globalPos())
            event.accept()

    def index_at(self, position):
        plan = self.geometry_plan
        if not plan or position.x() < 0 or position.y() < 0:
            return None
        column = position.x() // plan.column_width
        row = position.y() // self.row_height
        if column >= plan.columns or row >= plan.rows:
            return None
        index = self.logical_column(column) * plan.rows + row
        if index >= len(self.entries):
            return None
        return index

    def logical_column(self, column):
        return self.geometry_plan.columns - 1 - column if self.right_to_left else column

    def visual_column(self, column):
        return self.logical_column(column)

    def boundary_at(self, position):
        plan = self.geometry_plan
        if not self.entries:
            return 0, 0, 0
        if not plan:
            return None
        column = max(0, min(plan.columns - 1, position.x() // plan.column_width))
        row = max(0, min(plan.rows, (position.y() + self.row_height // 2) // self.row_height))
        logical = self.logical_column(column)
        boundary = min(len(self.entries), logical * plan.rows + row)
        # Keep the visual line at the end of this column when crossing its last row.
        visual_row = boundary - logical * plan.rows
        if visual_row < 0:
            return None
        return boundary, column, visual_row

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        index = self.index_at(event.position().toPoint())
        self.pending_single = None
        self.press_position = None
        if index is None or self.entries[index].category:
            return
        modifiers = event.modifiers()
        if modifiers & Qt.ShiftModifier and self.anchor is not None:
            start, end = sorted((self.anchor, index))
            group = {i for i in range(start, end + 1) if not self.entries[i].category}
            self.selected = self.selected | group if modifiers & Qt.ControlModifier else group
        elif modifiers & Qt.ControlModifier:
            self.selected.symmetric_difference_update({index})
            self.anchor = index
        else:
            if index in self.selected:
                # Preserve the group until we know whether this is a click or a drag.
                self.pending_single = index
            else:
                self.selected = {index}
            self.anchor = index
        if index in self.selected:
            self.press_position = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.pending_single is not None:
                self.selected = {self.pending_single}
            self.pending_single = None
            self.press_position = None
            self.update()
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if (self.press_position is not None and event.buttons() & Qt.LeftButton
                and (event.position().toPoint() - self.press_position).manhattanLength()
                >= QApplication.startDragDistance()):
            self.press_position = None
            self.pending_single = None
            self.drag_indices = sorted(self.selected)
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(self.drag_format, b"internal")
            drag.setMimeData(mime)
            try:
                drag.exec(Qt.MoveAction)
            finally:
                self.drag_indices = None
                self.clear_drag_feedback()
        super().mouseMoveEvent(event)

    def accepts_drag(self, event):
        return (event.source() is self and self.drag_indices is not None
                and event.mimeData().hasFormat(self.drag_format))

    def dropped_paths(self, event):
        mime = event.mimeData()
        if mime.hasFormat(self.drag_format) or not mime.hasUrls():
            return []
        urls = mime.urls()
        if not urls or any(not url.isLocalFile() for url in urls):
            return []
        paths = [Path(url.toLocalFile()) for url in urls]
        return [path for path in paths if path.is_dir() or (path.is_file() and is_supported_song(path))]

    def dragEnterEvent(self, event):
        if self.accepts_drag(event):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        elif self.dropped_paths(event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        internal = self.accepts_drag(event)
        if not internal and not self.dropped_paths(event):
            event.ignore()
            return
        position = event.position().toPoint()
        self.insertion = self.boundary_at(position)
        area = self.parentWidget().parentWidget()
        viewport_x = position.x() - area.horizontalScrollBar().value()
        self.scroll_direction = -1 if viewport_x < 24 else (1 if viewport_x > area.viewport().width() - 24 else 0)
        if self.scroll_direction:
            self.scroll_timer.start()
        else:
            self.scroll_timer.stop()
        event.setDropAction(Qt.MoveAction if internal else Qt.CopyAction)
        event.accept()
        self.update()

    def scroll_during_drag(self):
        area = self.parentWidget().parentWidget()
        bar = area.horizontalScrollBar()
        bar.setValue(bar.value() + self.scroll_direction * 18)
        self.insertion = self.boundary_at(self.mapFromGlobal(QCursor.pos()))
        self.update()

    def clear_drag_feedback(self):
        self.insertion = None
        self.scroll_timer.stop()
        self.scroll_direction = 0
        self.update()

    def dragLeaveEvent(self, event):
        self.clear_drag_feedback()
        event.accept()

    def dropEvent(self, event):
        insertion = self.boundary_at(event.position().toPoint())
        if self.accepts_drag(event) and insertion is not None:
            self.moveRequested.emit(self.drag_indices, insertion[0])
            event.setDropAction(Qt.MoveAction)
            event.accept()
        elif insertion is not None and (paths := self.dropped_paths(event)):
            if all(path.is_dir() for path in paths):
                self.foldersDropped.emit(paths, insertion[0])
            else:
                self.pathsDropped.emit(paths, insertion[0])
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()
        self.clear_drag_feedback()

    @property
    def row_height(self):
        return max(18, self.fontMetrics().height() + 10)

    def set_font_size(self, size):
        font = QFont(self.font())
        font.setPointSize(max(6, min(32, size)))
        self.setFont(font)

    def arrange(self, width, height):
        minimum = max(120, round(190 * self.font().pointSize() / 10),
                      self.fontMetrics().horizontalAdvance("מ") * 20)
        self.geometry_plan = calculate_layout(len(self.entries), width, height,
                                               self.row_height, minimum, self.column_width_override)
        self.setFixedSize(QSize(self.geometry_plan.content_width, max(1, height)))
        self.update()

    def category_rect(self, rect, depth):
        width = round(rect.width() * (1.0, 0.80, 0.60)[min(2, max(0, depth))])
        result = QRect(rect)
        result.setWidth(width)
        if self.right_to_left:
            result.moveRight(rect.right())
        return result

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101923"))
        if not self.entries or not self.geometry_plan:
            painter.setPen(QColor("#b2c2d2"))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Drop songs or folders here\nRight-click to add a song or category")
            return
        plan = self.geometry_plan
        for index, entry in enumerate(self.entries):
            column, row = divmod(index, plan.rows)
            column = self.visual_column(column)
            rect = QRect(column * plan.column_width + 4, row * self.row_height + 2,
                         plan.column_width - 8, self.row_height - 4)
            if not rect.intersects(event.rect()):
                continue
            if entry.category:
                rect = self.category_rect(rect, entry.depth)
            painter.fillRect(rect, QColor("#254d59" if entry.category else
                                         ("#1b2836" if row % 2 == 0 else "#16222f")))
            if index in self.selected:
                painter.fillRect(rect, QColor("#315f86"))
                painter.setPen(QPen(QColor("#8fcbff"), 2))
                painter.drawRect(rect.adjusted(1, 1, -1, -1))
            font = QFont(self.font())
            font.setBold(entry.category)
            painter.setFont(font)
            text_rect = rect.adjusted(7, 0, -7, 0)
            if not entry.category:
                number_width = max(36, self.fontMetrics().horizontalAdvance(str(len(self.entries))) + 10)
                painter.setPen(QColor("#8da2b7"))
                painter.drawText(QRect(rect.right() - number_width + 2, rect.top(), number_width - 7, rect.height()),
                                 Qt.AlignRight | Qt.AlignVCenter, str(entry.number))
                text_rect.adjust(0, 0, -number_width, 0)
            painter.setPen(QColor("#a9efdf" if entry.category else "#e6edf5"))
            label = painter.fontMetrics().elidedText(entry.name, Qt.ElideLeft, text_rect.width())
            alignment = Qt.AlignCenter if entry.category else Qt.AlignRight | Qt.AlignVCenter
            prefix = "\u200f" if not entry.category or not entry.depth or self.right_to_left else "\u200e"
            painter.drawText(text_rect, alignment, prefix + label)
        if self.insertion is not None:
            _, column, row = self.insertion
            x = column * plan.column_width + 4
            y = min(self.height() - 2, max(2, row * self.row_height))
            painter.setPen(QPen(QColor("#ffc857"), 3))
            painter.drawLine(x, y, x + plan.column_width - 8, y)
            painter.drawLine(x, y - 4, x, y + 4)
            painter.drawLine(x + plan.column_width - 8, y - 4, x + plan.column_width - 8, y + 4)

    def event(self, event):
        if event.type() == QEvent.ToolTip and self.geometry_plan:
            index = self.index_at(event.pos())
            if index is not None:
                entry = self.entries[index]
                QToolTip.showText(event.globalPos(), entry.name, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(event)


class MapArea(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.LeftToRight)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.NoFrame)
        self.map = PlaylistMap()
        self.setWidget(self.map)
        self.map.installEventFilter(self)

    def viewportEvent(self, event):
        result = super().viewportEvent(event)
        if event.type() == QEvent.Resize and hasattr(self, "map"):
            self.reflow()
        return result

    def eventFilter(self, watched, event):
        if watched is self.map and event.type() == QEvent.FontChange:
            self.reflow()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        self.map.arrange(self.viewport().width(), self.viewport().height())

    def set_entries(self, entries):
        self.map.reset_selection()
        self.map.entries = entries
        self.reflow()
        self.scroll_to_start()

    def scroll_to_start(self):
        bar = self.horizontalScrollBar()
        bar.setValue(bar.maximum() if self.map.right_to_left else 0)

    def set_column_direction(self, right_to_left):
        self.map.right_to_left = right_to_left
        self.map.clear_drag_feedback()
        self.reflow()
        self.scroll_to_start()
