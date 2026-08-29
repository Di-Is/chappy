"""Shared placement of rotated component labels for spectrum plots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from matplotlib.axes import Axes
    from matplotlib.text import Annotation

DEFAULT_COMPONENT_LABEL_BAND_TOP = 0.985
_BAND_BOTTOM = 0.75
_FONT_SIZE = 7
# Measured: a rotated 7pt label is 7.2pt across whatever its text reads, bbox pad included.
# Dividing its pixel width by this yields the figure's pixels-per-point without a dpi lookup.
_LABEL_WIDTH_POINTS = 7.2
_LABEL_GAP_POINTS = 1.8
_LABEL_PITCH_POINTS = _LABEL_WIDTH_POINTS + _LABEL_GAP_POINTS
_MAX_SHIFT_POINTS = 24.0
_ROW_GAP_POINTS = 3.0
_TOP_MARGIN_POINTS = 3.0
_BASE_ZORDER = 6
_SELECTED_ZORDER = 16
_LABEL_BBOX = {
    "boxstyle": "round,pad=0.2",
    "fc": "white",
    "ec": "#3C4043",
    "linewidth": 0.5,
    "alpha": 0.96,
}


@dataclass(frozen=True, slots=True)
class ComponentLabelEntry:
    """One component label request: where it points, what it reads, and its emphasis."""

    x: float
    text: str
    short_text: str | None = None
    selected: bool = False
    color: str | None = None


def place_rotated_component_labels(
    axes: Axes,
    entries: Sequence[ComponentLabelEntry],
    *,
    color: str,
    band_top: float = DEFAULT_COMPONENT_LABEL_BAND_TOP,
) -> list[Annotation]:
    """Annotate each entry rotated below ``band_top``, nudging crowded neighbors apart.

    ``color`` is the fallback; an entry carrying its own colour keeps it.

    Labels hang downward from the band top so they never collide with the title. Entries
    closer together than one label width are pushed sideways as a group balanced around
    their original positions. When that group would move too far, or the text is too long
    for the band, non-selected entries fall back to their short text and alternate onto a
    second row. A selected entry keeps its full text on the first row and reads bold.
    Returns the annotations in input order.
    """
    if not entries:
        return []

    annotations = [_annotate(axes, entry, color=color, band_top=band_top) for entry in entries]
    pixels_per_point = float(annotations[0].get_window_extent().width) / _LABEL_WIDTH_POINTS
    x_points = [
        float(axes.transData.transform((entry.x, 0.0))[0]) / pixels_per_point for entry in entries
    ]
    clusters = _cluster_indices(x_points)

    rows = [0] * len(entries)
    shifts = _resolve_shifts(x_points, clusters, rows)
    lengths = [_length_points(annotation, pixels_per_point) for annotation in annotations]
    band_height = (
        (band_top - _BAND_BOTTOM) * float(axes.get_window_extent().height) / pixels_per_point
    )
    if max(abs(shift) for shift in shifts) > _MAX_SHIFT_POINTS or max(lengths) > band_height:
        for entry, annotation in zip(entries, annotations, strict=True):
            if not entry.selected and entry.short_text is not None:
                annotation.set_text(entry.short_text)
        rows = _assign_rows(entries, clusters)
        shifts = _resolve_shifts(x_points, clusters, rows)

    row_pitch = _ROW_GAP_POINTS + max(
        (
            _length_points(annotation, pixels_per_point)
            for annotation, row in zip(annotations, rows, strict=True)
            if row == 0
        ),
        default=0.0,
    )
    for annotation, shift, row in zip(annotations, shifts, rows, strict=True):
        annotation.xyann = (shift, -_TOP_MARGIN_POINTS - row * row_pitch)
    return annotations


def _annotate(
    axes: Axes, entry: ComponentLabelEntry, *, color: str, band_top: float
) -> Annotation:
    """Create one rotated annotation anchored at the band top."""
    return axes.annotate(
        entry.text,
        xy=(entry.x, band_top),
        xycoords=("data", "axes fraction"),
        xytext=(0.0, -_TOP_MARGIN_POINTS),
        textcoords="offset points",
        rotation=90,
        ha="center",
        va="top",
        fontsize=_FONT_SIZE,
        fontweight="bold" if entry.selected else "normal",
        color=entry.color or color,
        bbox=_LABEL_BBOX,
        zorder=_SELECTED_ZORDER if entry.selected else _BASE_ZORDER,
    )


def _length_points(annotation: Annotation, pixels_per_point: float) -> float:
    """Return how far a rotated annotation reads downward, in points."""
    return float(annotation.get_window_extent().height) / pixels_per_point


def _cluster_indices(x_points: Sequence[float]) -> list[list[int]]:
    """Group indices whose neighbors sit closer than one label pitch, in ascending x order."""
    order = sorted(range(len(x_points)), key=lambda index: x_points[index])
    clusters: list[list[int]] = [[order[0]]]
    for index in order[1:]:
        if x_points[index] - x_points[clusters[-1][-1]] < _LABEL_PITCH_POINTS:
            clusters[-1].append(index)
        else:
            clusters.append([index])
    return clusters


def _assign_rows(
    entries: Sequence[ComponentLabelEntry], clusters: Sequence[list[int]]
) -> list[int]:
    """Alternate crowded cluster members between two rows, keeping selected entries on top."""
    rows = [0] * len(entries)
    for cluster in clusters:
        row = 0
        for index in cluster:
            if entries[index].selected:
                rows[index] = 0
                row = 1
            else:
                rows[index] = row
                row = 1 - row
    return rows


def _resolve_shifts(
    x_points: Sequence[float], clusters: Sequence[list[int]], rows: Sequence[int]
) -> list[float]:
    """Return each label's horizontal offset in points from its own x position."""
    shifts = [0.0] * len(x_points)
    for cluster in clusters:
        for row in sorted({rows[index] for index in cluster}):
            members = [index for index in cluster if rows[index] == row]
            _spread_members(x_points, members, shifts)
    return shifts


def _spread_members(
    x_points: Sequence[float], members: Sequence[int], shifts: list[float]
) -> None:
    """Sweep one row of a cluster apart, then re-center it on its original span."""
    positions: list[float] = []
    for index in members:
        desired = x_points[index]
        positions.append(
            desired if not positions else max(desired, positions[-1] + _LABEL_PITCH_POINTS)
        )
    bias = sum(
        position - x_points[index] for position, index in zip(positions, members, strict=True)
    ) / len(members)
    for position, index in zip(positions, members, strict=True):
        shifts[index] = position - x_points[index] - bias
