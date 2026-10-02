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
    available_columns = max(1, width // minimum_width)
    # Fill the screen with more columns when the entire document fits.
    if columns <= available_columns:
        columns = min(max(1, count), available_columns)
        rows = max(1, ceil(count / columns))
    column_width = fixed_width if fixed_width is not None else max(minimum_width, width // columns)
    return ColumnLayout(rows, columns, column_width, columns * column_width)
