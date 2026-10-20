#
# This module holds the content elements a test may report
#
# Design decisions (see .agents/skills/high-level-design/SKILL.md, "Reporting"):
#
# - Tests can only report a limited set of content: Text, Table, Chart and
#   Image (verdicts are reported as events, see events.py). Keeping the set
#   small means every report module can render every element in some form.
#
# - A Table has two variants:
#     * simple: every cell is a scalar (str, int, float, bool or None) and is
#       rendered as text. Every report module supports simple tables.
#     * complex: a cell may also hold any Element, including another Table.
#       Modules that cannot nest (console, Excel) fall back to Element.to_text().
#   Both variants are the same class; `Table.is_simple` tells them apart, so a
#   test never needs to pick a variant up front.
#
# - A Chart is plain data (named x/y series plus labels), never a rendered
#   picture, so every module can draw or summarize it with its own tools.
#
# - An Image references a file or holds raw bytes. Its use case is still
#   unclear in the design, so it is kept minimal.
#

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence, Union

Scalar = Union[str, int, float, bool, None]

CHART_KINDS = ("line", "scatter", "bar")


class Element:
    """Base class for content that can be added to a report."""

    def to_text(self) -> str:
        """A plain text fallback for modules that cannot render this element."""
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable representation, tagged with the element type."""
        raise NotImplementedError


@dataclass
class Text(Element):
    """A block of free text."""

    text: str

    def __post_init__(self) -> None:
        self.text = str(self.text)

    def to_text(self) -> str:
        return self.text

    def to_dict(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


Cell = Union[Scalar, Element]


@dataclass
class Table(Element):
    """A table of rows, optionally with a header row and a title.

    Cells are scalars for a simple table. A complex table may also hold any
    :class:`Element` in a cell, including nested tables::

        Table([["U", 4.9], ["I", 0.2]], headers=["Signal", "Value"])
        Table([["trace", Chart("Ramp", [Series("U", [0, 1], [0, 5])])]])
    """

    rows: list[list[Cell]]
    headers: list[str] | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.rows, (str, bytes)) or not isinstance(self.rows, Sequence):
            raise TypeError("Table rows must be a sequence of rows")
        rows = []
        for row in self.rows:
            if isinstance(row, (str, bytes)) or not isinstance(row, Sequence):
                raise TypeError(f"Table row must be a sequence of cells, got {row!r}")
            for cell in row:
                if not isinstance(cell, (str, int, float, bool, type(None), Element)):
                    raise TypeError(
                        f"Table cell must be a scalar or report Element, got {type(cell).__name__}"
                    )
            rows.append(list(row))
        self.rows = rows
        if self.headers is not None:
            self.headers = [str(header) for header in self.headers]

    @property
    def is_simple(self) -> bool:
        """True if every cell is a scalar, i.e. the table is text only."""
        return not any(isinstance(cell, Element) for row in self.rows for cell in row)

    @property
    def column_count(self) -> int:
        widths = [len(row) for row in self.rows]
        if self.headers is not None:
            widths.append(len(self.headers))
        return max(widths, default=0)

    def text_rows(self) -> list[list[str]]:
        """Rows with every cell flattened to text, padded to equal length."""
        width = self.column_count
        return [[cell_text(cell) for cell in row] + [""] * (width - len(row)) for row in self.rows]

    def to_text(self) -> str:
        header = list(self.headers or [])
        rows = self.text_rows()
        width = self.column_count
        if header:
            header += [""] * (width - len(header))
        lines_per_row = [[cell.splitlines() or [""] for cell in row] for row in ([header] if header else []) + rows]
        widths = [0] * width
        for row in lines_per_row:
            for index, lines in enumerate(row):
                widths[index] = max(widths[index], *(len(line) for line in lines))

        out = []
        if self.title:
            out.append(self.title)
        separator = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        out.append(separator)
        for row_index, row in enumerate(lines_per_row):
            height = max((len(lines) for lines in row), default=1)
            for line_index in range(height):
                parts = [
                    (lines[line_index] if line_index < len(lines) else "").ljust(widths[index])
                    for index, lines in enumerate(row)
                ]
                out.append("| " + " | ".join(parts) + " |")
            if header and row_index == 0:
                out.append(separator.replace("-", "="))
        out.append(separator)
        return "\n".join(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "table",
            "title": self.title,
            "headers": self.headers,
            "rows": [[cell.to_dict() if isinstance(cell, Element) else cell for cell in row] for row in self.rows],
        }


@dataclass
class Series:
    """One named data series of a chart."""

    name: str
    x: list[float]
    y: list[float]

    def __post_init__(self) -> None:
        self.x = list(self.x)
        self.y = list(self.y)
        if len(self.x) != len(self.y):
            raise ValueError(
                f"Series {self.name!r} has {len(self.x)} x value(s) but {len(self.y)} y value(s)"
            )


@dataclass
class Chart(Element):
    """A chart of one or more data series.

    ``kind`` is one of ``"line"``, ``"scatter"`` or ``"bar"``. For bar charts
    the x values may be category labels::

        Chart("Supply ramp", [Series("U", [0, 1, 2], [0.0, 2.4, 4.9])], x_label="s", y_label="V")
    """

    title: str
    series: list[Series] = field(default_factory=list)
    x_label: str = ""
    y_label: str = ""
    kind: str = "line"

    def __post_init__(self) -> None:
        if self.kind not in CHART_KINDS:
            raise ValueError(f"Unknown chart kind {self.kind!r}; expected one of: {', '.join(CHART_KINDS)}")
        self.series = list(self.series)
        for series in self.series:
            if not isinstance(series, Series):
                raise TypeError(f"Chart series must be Series objects, got {type(series).__name__}")

    def to_text(self) -> str:
        lines = [f"Chart: {self.title} ({self.kind})"]
        for series in self.series:
            if series.y:
                lines.append(
                    f"  {series.name}: {len(series.y)} point(s), "
                    f"min {min(series.y):g}, max {max(series.y):g}"
                )
            else:
                lines.append(f"  {series.name}: no data")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "chart",
            "title": self.title,
            "kind": self.kind,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "series": [{"name": s.name, "x": s.x, "y": s.y} for s in self.series],
        }


@dataclass
class Image(Element):
    """An image, given as a file path or as raw bytes with a MIME type."""

    path: Path | None = None
    data: bytes | None = None
    mime_type: str = "image/png"
    caption: str = ""

    def __post_init__(self) -> None:
        if (self.path is None) == (self.data is None):
            raise ValueError("Image needs exactly one of path or data")
        if self.path is not None:
            self.path = Path(self.path)

    def read_bytes(self) -> bytes:
        return self.data if self.data is not None else self.path.read_bytes()

    def to_text(self) -> str:
        source = str(self.path) if self.path is not None else f"{len(self.data)} bytes"
        return f"Image: {self.caption or source}" + (f" ({source})" if self.caption else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "image",
            "path": str(self.path) if self.path is not None else None,
            "mime_type": self.mime_type,
            "caption": self.caption,
        }


def cell_text(cell: Cell) -> str:
    """Render a table cell as text."""
    if isinstance(cell, Element):
        return cell.to_text()
    if cell is None:
        return ""
    return str(cell)
