#
# This module holds the HTML report module
#
# Design decisions:
# - The report is one self-contained HTML file (inline CSS, charts as inline
#   SVG, images embedded as data URIs), so it can be archived or mailed with
#   the test results without losing anything. No third party dependencies.
# - Groups and tests are collapsible <details> blocks; failed tests start
#   open so the diagnosis is visible first.
# - Complex tables are rendered natively: a cell holding an element renders
#   that element, including nested tables.
#

from __future__ import annotations

import base64
import datetime
import html
from pathlib import Path

from fixturerig.base.verdict import VerdictStatus
from fixturerig.report.elements import Chart, Element, Image, Table, Text, cell_text
from fixturerig.report.events import ContentEvent, VerdictEvent
from fixturerig.report.recording import GroupRecord, RecordingReport, RunRecord, TestRecord

_PALETTE = ["#2a6fdb", "#e0782b", "#2a9d5c", "#c03b5a", "#7b52c4", "#8a7a2a"]

_CSS = """
:root { --fg:#1d2329; --muted:#5d6874; --line:#d5dae0; --bg:#ffffff; --panel:#f5f7f9;
  --passed:#1f8a4c; --failed:#c62f2f; --error:#9c1c1c; --skipped:#b07800; --none:#8a3fa0; --knownfailed:#2a7f8f; }
body { font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--fg);
  background: var(--bg); margin: 0 auto; max-width: 1100px; padding: 24px 16px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.meta { color: var(--muted); margin-bottom: 16px; }
.summary { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.summary span { padding: 4px 10px; border-radius: 4px; background: var(--panel); }
details { border: 1px solid var(--line); border-radius: 6px; margin: 8px 0; background: var(--bg); }
details > summary { cursor: pointer; padding: 8px 12px; list-style: none; display: flex; gap: 10px;
  align-items: baseline; flex-wrap: wrap; }
details > summary::-webkit-details-marker { display: none; }
details > summary::before { content: "\\25B8"; color: var(--muted); }
details[open] > summary::before { content: "\\25BE"; }
.group > summary { font-weight: 600; background: var(--panel); }
.body { padding: 4px 16px 12px; }
.badge { font-size: 12px; font-weight: 600; padding: 1px 8px; border-radius: 10px; color: #fff;
  text-transform: uppercase; }
.dur, .cls { color: var(--muted); font-size: 12px; }
.msg { color: var(--muted); }
.spec { color: var(--muted); white-space: pre-wrap; margin: 4px 0 8px; }
.trace { font-size: 12px; }
.text { white-space: pre-wrap; margin: 6px 0; }
.check { margin: 4px 0; }
table { border-collapse: collapse; margin: 8px 0; }
th, td { border: 1px solid var(--line); padding: 3px 8px; text-align: left; vertical-align: top; }
th { background: var(--panel); }
caption { text-align: left; font-weight: 600; padding: 2px 0; }
figure { margin: 8px 0; }
figcaption { color: var(--muted); font-size: 12px; }
img { max-width: 100%; }
svg text { font: 11px system-ui, sans-serif; fill: var(--muted); }
""" + "".join(
    f".s-{status.value} {{ background: var(--{status.value}); }}\n" for status in VerdictStatus
)


class HtmlReport(RecordingReport):
    """Writes a self-contained HTML report.

    :param path: the file to write.
    :param title: the report heading; defaults to the run title.
    """

    def __init__(self, path: Path = Path("fixturerig-report.html"), title: str = "", **kwargs):
        super().__init__(**kwargs)
        self.path = Path(path)
        self.title = title

    def write(self, run: RunRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(render_run(run, self.title or run.title), encoding="utf-8")


def render_run(run: RunRecord, title: str) -> str:
    started = (
        datetime.datetime.fromtimestamp(run.started.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        if run.started
        else "-"
    )
    duration = f"{run.finished.duration:.2f}s" if run.finished else "aborted"
    counts = run.counts()
    summary = "".join(
        f'<span><span class="badge s-{_esc(status)}">{_esc(status)}</span> {count}</span>'
        for status, count in counts.items()
    ) or "<span>no tests</span>"
    body = "".join(_render_item(child) for child in run.root.children)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f'<div class="meta">Started {started} &middot; {sum(counts.values())} test(s) &middot; {duration}</div>'
        f'<div class="summary">{summary}</div>{body}</body></html>\n'
    )


def _render_item(item: GroupRecord | TestRecord | ContentEvent) -> str:
    if isinstance(item, GroupRecord):
        return _render_group(item)
    if isinstance(item, TestRecord):
        return _render_test(item)
    return _render_content(item)


def _render_group(group: GroupRecord) -> str:
    tests = list(group.tests())
    bad = [t for t in tests if t.status is not VerdictStatus.PASSED]
    open_attr = " open" if bad else ""
    duration = f'<span class="dur">{group.finished.duration:.2f}s</span>' if group.finished else ""
    stats = f'<span class="dur">{len(tests) - len(bad)}/{len(tests)} passed</span>'
    children = "".join(_render_item(child) for child in group.children)
    return (
        f'<details class="group"{open_attr}><summary>{_esc(group.name or "(group)")}'
        f"{stats}{duration}</summary><div class=\"body\">{children}</div></details>"
    )


def _render_test(test: TestRecord) -> str:
    spec = test.started
    status = test.status or VerdictStatus.NONE
    message = test.finished.verdict.message if test.finished else "test did not finish"
    open_attr = "" if status is VerdictStatus.PASSED else " open"
    duration = f'<span class="dur">{test.finished.duration:.3f}s</span>' if test.finished else ""
    parts = []
    if spec.description:
        parts.append(f'<div class="spec">{_esc(spec.description)}</div>')
    if spec.traceability:
        parts.append(f'<div class="trace">Traceability: {_esc(", ".join(spec.traceability))}</div>')
    if spec.params:
        rows = [[name, repr(value)] for name, value in spec.params.items()]
        parts.append(_render_table(Table(rows, headers=["Parameter", "Value"])))
    parts.extend(_render_content(event) for event in test.content)
    return (
        f'<details class="test"{open_attr}><summary>'
        f'<span class="badge s-{status.value}">{status.value}</span>'
        f"<strong>{_esc(spec.name)}</strong>"
        f'<span class="cls">{_esc(spec.cls)}</span>{duration}'
        f'<span class="msg">{_esc(message)}</span></summary>'
        f'<div class="body">{"".join(parts)}</div></details>'
    )


def _render_content(event: ContentEvent) -> str:
    if isinstance(event, VerdictEvent):
        status = event.verdict.status.value
        return (
            f'<div class="check"><span class="badge s-{status}">{status}</span> '
            f"{_esc(event.verdict.message)}</div>"
        )
    return render_element(event.element) if event.element is not None else ""


def render_element(element: Element) -> str:
    if isinstance(element, Text):
        return f'<div class="text">{_esc(element.text)}</div>'
    if isinstance(element, Table):
        return _render_table(element)
    if isinstance(element, Chart):
        return f"<figure>{chart_svg(element)}</figure>"
    if isinstance(element, Image):
        return _render_image(element)
    return f'<div class="text">{_esc(element.to_text())}</div>'


def _render_table(table: Table) -> str:
    out = ["<table>"]
    if table.title:
        out.append(f"<caption>{_esc(table.title)}</caption>")
    if table.headers:
        out.append("<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in table.headers) + "</tr>")
    width = table.column_count
    for row in table.rows:
        cells = [render_element(c) if isinstance(c, Element) else _esc(cell_text(c)) for c in row]
        cells += [""] * (width - len(cells))
        out.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _render_image(image: Image) -> str:
    try:
        data = base64.b64encode(image.read_bytes()).decode("ascii")
    except OSError as exc:
        return f'<div class="text">Image {_esc(str(image.path))} could not be read: {_esc(str(exc))}</div>'
    caption = f"<figcaption>{_esc(image.caption)}</figcaption>" if image.caption else ""
    return (
        f'<figure><img alt="{_esc(image.caption)}" src="data:{_esc(image.mime_type)};base64,{data}">'
        f"{caption}</figure>"
    )


def chart_svg(chart: Chart, width: int = 640, height: int = 320) -> str:
    """Render a chart as an inline SVG with axes, ticks and a legend."""
    left, right, top, bottom = 56, 16, 28, 44
    plot_w, plot_h = width - left - right, height - top - bottom
    series = [s for s in chart.series if s.y]
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{_esc(chart.title)}">',
        f'<text x="{left}" y="16" style="font-weight:600">{_esc(chart.title)}</text>',
    ]
    if not series:
        out.append(f'<text x="{left}" y="{top + 20}">no data</text></svg>')
        return "".join(out)

    ys = [float(y) for s in series for y in s.y]
    y_min, y_max = min(ys), max(ys)
    if chart.kind == "bar":
        y_min = min(0.0, y_min)
        y_max = max(0.0, y_max)
    if y_min == y_max:
        y_min, y_max = y_min - 1, y_max + 1

    def py(y: float) -> float:
        return top + plot_h - (float(y) - y_min) / (y_max - y_min) * plot_h

    # Axes and horizontal grid with 5 ticks.
    out.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#8892a0"/>'
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#8892a0"/>'
    )
    for i in range(5):
        value = y_min + (y_max - y_min) * i / 4
        y = py(value)
        out.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="#d5dae0" stroke-dasharray="2,3"/>'
            f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{value:.4g}</text>'
        )

    if chart.kind == "bar":
        categories: list = []
        for s in series:
            for x in s.x:
                if x not in categories:
                    categories.append(x)
        slot = plot_w / len(categories)
        bar_w = slot * 0.8 / len(series)
        zero = py(0.0)
        for si, s in enumerate(series):
            color = _PALETTE[si % len(_PALETTE)]
            for x, y in zip(s.x, s.y):
                xi = categories.index(x)
                bx = left + xi * slot + slot * 0.1 + si * bar_w
                y0, y1 = sorted((zero, py(y)))
                out.append(
                    f'<rect x="{bx:.1f}" y="{y0:.1f}" width="{bar_w:.1f}" height="{y1 - y0:.1f}" fill="{color}">'
                    f"<title>{_esc(s.name)} {_esc(str(x))}: {y:g}</title></rect>"
                )
        for xi, x in enumerate(categories):
            cx = left + (xi + 0.5) * slot
            out.append(f'<text x="{cx:.1f}" y="{top + plot_h + 16}" text-anchor="middle">{_esc(str(x))}</text>')
    else:
        xs = [float(x) for s in series for x in s.x]
        x_min, x_max = min(xs), max(xs)
        if x_min == x_max:
            x_min, x_max = x_min - 1, x_max + 1

        def px(x: float) -> float:
            return left + (float(x) - x_min) / (x_max - x_min) * plot_w

        for i in range(5):
            value = x_min + (x_max - x_min) * i / 4
            out.append(
                f'<text x="{px(value):.1f}" y="{top + plot_h + 16}" text-anchor="middle">{value:.4g}</text>'
            )
        for si, s in enumerate(series):
            color = _PALETTE[si % len(_PALETTE)]
            points = [(px(x), py(y)) for x, y in zip(s.x, s.y)]
            if chart.kind == "line":
                coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                out.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2"/>')
            for (x, y), raw_x, raw_y in zip(points, s.x, s.y):
                radius = 3 if chart.kind == "scatter" else 2
                out.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}">'
                    f"<title>{_esc(s.name)}: ({raw_x:g}, {raw_y:g})</title></circle>"
                )

    if chart.x_label:
        out.append(
            f'<text x="{left + plot_w / 2:.1f}" y="{height - 8}" text-anchor="middle">{_esc(chart.x_label)}</text>'
        )
    if chart.y_label:
        out.append(
            f'<text x="12" y="{top + plot_h / 2:.1f}" text-anchor="middle" '
            f'transform="rotate(-90 12 {top + plot_h / 2:.1f})">{_esc(chart.y_label)}</text>'
        )
    legend_x = left + plot_w
    for si, s in enumerate(reversed(series)):
        index = len(series) - 1 - si
        legend_x -= 14 + 7 * len(s.name) + 12
        out.append(
            f'<rect x="{legend_x:.0f}" y="8" width="10" height="10" fill="{_PALETTE[index % len(_PALETTE)]}"/>'
            f'<text x="{legend_x + 14:.0f}" y="17">{_esc(s.name)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)
