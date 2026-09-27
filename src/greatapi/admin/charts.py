"""Server-rendered inline SVG charts.

No chart library and no CDN: the admin has to work behind a strict
Content-Security-Policy and on a machine with no internet. Everything here
returns markup that is embedded directly in the page and styled with the same
CSS custom properties as the rest of the UI, so charts follow the light/dark
theme for free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from math import ceil

from markupsafe import Markup

__all__ = ["Series", "bar_chart", "line_chart", "sparkline"]


@dataclass(slots=True)
class Series:
    """Labelled values for a chart."""

    labels: list[str]
    values: list[float]

    @property
    def maximum(self) -> float:
        return max(self.values) if self.values else 0.0


def _empty(message: str = "No data yet") -> Markup:
    return Markup(f'<p class="chart-empty">{escape(message)}</p>')


def sparkline(values: list[float], *, width: int = 120, height: int = 32) -> Markup:
    """A tiny trend line for stat tiles."""
    if len(values) < 2:
        return Markup('<svg class="sparkline" role="presentation" aria-hidden="true"></svg>')

    peak = max(values) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(
        f"{index * step:.2f},{height - (value / peak) * (height - 2) - 1:.2f}"
        for index, value in enumerate(values)
    )
    return Markup(
        f'<svg class="sparkline" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="presentation" aria-hidden="true">'
        f'<polyline points="{points}" fill="none" stroke="currentColor" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def bar_chart(series: Series, *, height: int = 200, unit: str = "") -> Markup:
    """A vertical bar chart with an accessible table fallback."""
    if not series.values or series.maximum <= 0:
        return _empty()

    count = len(series.values)
    gap = 6
    width = max(240, count * 34)
    bar_width = (width - gap * (count - 1)) / count
    peak = series.maximum
    plot_height = height - 24

    bars: list[str] = []
    for index, (label, value) in enumerate(zip(series.labels, series.values, strict=False)):
        bar_height = max(1.0, (value / peak) * plot_height)
        x = index * (bar_width + gap)
        y = plot_height - bar_height
        title = f"{escape(label)}: {_format(value)}{escape(unit)}"
        bars.append(
            f'<g class="bar"><title>{title}</title>'
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" '
            f'rx="3"/></g>'
        )

    # A label needs roughly 6px per character. When the bars are narrower than
    # that, print every Nth instead of letting them overlap into mush.
    per_label_width = bar_width + gap
    stride = max(1, ceil(38 / per_label_width))
    labels = "".join(
        f'<text x="{index * per_label_width + bar_width / 2:.2f}" y="{height - 6}" '
        f'text-anchor="middle" class="chart-label">{escape(_short(label))}</text>'
        for index, label in enumerate(series.labels)
        if index % stride == 0 or index == count - 1
    )

    return Markup(
        f'<svg class="chart chart-bar" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Bar chart">{"".join(bars)}{labels}</svg>'
    )


def line_chart(series: Series, *, height: int = 200, unit: str = "") -> Markup:
    """A filled line chart for time series."""
    if len(series.values) < 2:
        return _empty()

    width = 640
    peak = series.maximum or 1.0
    plot_height = height - 24
    step = width / (len(series.values) - 1)

    coordinates = [
        (index * step, plot_height - (value / peak) * (plot_height - 4))
        for index, value in enumerate(series.values)
    ]
    line = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
    area = f"0,{plot_height} {line} {width},{plot_height}"

    dots = "".join(
        f'<g class="dot"><title>{escape(label)}: {_format(value)}{escape(unit)}</title>'
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3"/></g>'
        for (x, y), label, value in zip(coordinates, series.labels, series.values, strict=False)
    )

    first, last = series.labels[0], series.labels[-1]
    axis = (
        f'<text x="0" y="{height - 6}" class="chart-label">{escape(_short(first))}</text>'
        f'<text x="{width}" y="{height - 6}" text-anchor="end" class="chart-label">'
        f"{escape(_short(last))}</text>"
    )

    return Markup(
        f'<svg class="chart chart-line" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" role="img" aria-label="Line chart">'
        f'<polygon class="area" points="{area}"/>'
        f'<polyline class="line" points="{line}" fill="none"/>'
        f"{dots}{axis}</svg>"
    )


def _format(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}"
    if value == int(value):
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


#: ISO dates dominate these axes, and the year is identical on every tick.
_ISO_DATE = re.compile(r"^\d{4}-(\d{2})-(\d{2})$")


def _short(label: str, limit: int = 8) -> str:
    match = _ISO_DATE.match(label)
    if match:
        return f"{match.group(2)}/{match.group(1)}"
    return label if len(label) <= limit else label[: limit - 1] + "…"
