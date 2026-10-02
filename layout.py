"""Column-major geometry, independent of Qt and the document."""
from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class ColumnLayout:
    rows: int
    columns: int
    column_width: int
    content_width: int


def calculate_layout(count, width, height, row_height, minimum_width, fixed_width=None):
    if fixed_width is not None:
        minimum_width = fixed_width
    rows = max(1, height // row_height)
    columns = max(1, ceil(count / rows))
    column_width = minimum_width
    return ColumnLayout(rows, columns, column_width, columns * column_width)
