"""Identify-mode preview overlay support for Matplotlib spectrum plots."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

import numpy as np
from matplotlib import patches, transforms

if TYPE_CHECKING:
    from collections.abc import Sequence

    from matplotlib.axes import Axes
    from matplotlib.backend_bases import FigureCanvasBase
    from matplotlib.text import Text

    from chappy.plotting.components.selection_handler import RemovableArtist


class IdentifyPreviewEntry(TypedDict, total=False):
    """Entry describing a single identify-mode preview span."""

    lambda_min: float
    lambda_max: float
    center: float | None
    color: str
    fill_alpha: float
    line_alpha: float
    line_width: float
    line_style: str
    is_primary: bool
    label: str | None
    label_color: str
    label_font_size: float
    label_font_weight: str


class IdentifyPreviewPayload(TypedDict, total=False):
    """Collection of identify preview entries for rendering."""

    entries: Sequence[IdentifyPreviewEntry]
    hint_text: str


@dataclass
class IdentifyPreviewOverlay:
    """Maintain identify-mode ghost overlay artists."""

    axes: Axes
    canvas: FigureCanvasBase
    span_zorder_base: int = 7
    label_y: float = 0.955
    spans: list[RemovableArtist] = field(default_factory=list, init=False)
    patches_: list[RemovableArtist] = field(default_factory=list, init=False)
    lines: list[RemovableArtist] = field(default_factory=list, init=False)
    labels: list[Text] = field(default_factory=list, init=False)
    hint: Text | None = field(default=None, init=False)

    def set_preview(self, preview: IdentifyPreviewPayload | None) -> None:
        """Render identify-mode ghost overlays driven by cursor position."""
        self.clear()

        if preview is None:
            self.canvas.draw_idle()
            return

        entries = preview.get("entries", ())
        if not entries:
            self.canvas.draw_idle()
            return

        data_axes_transform = transforms.blended_transform_factory(
            self.axes.transData, self.axes.transAxes
        )

        for entry in entries:
            self._draw_entry(entry, data_axes_transform)

        hint_text = preview.get("hint_text")
        if hint_text:
            self._draw_hint(hint_text)

        self.canvas.draw_idle()

    def clear(self) -> None:
        """Remove previously rendered identify-mode overlays."""
        for collection in (self.spans, self.patches_, self.lines, self.labels):
            for item in collection:
                with contextlib.suppress(ValueError):
                    item.remove()
            collection.clear()
        if self.hint is not None:
            with contextlib.suppress(ValueError):
                self.hint.remove()
            self.hint = None

    def _draw_hint(self, hint_text: str) -> None:
        """Draw non-interactive guidance inside the normal spectrum axes."""
        self.hint = self.axes.text(
            0.02,
            0.03,
            hint_text,
            color="#F0F0F0",
            fontsize=9,
            ha="left",
            va="bottom",
            transform=self.axes.transAxes,
            zorder=self.span_zorder_base + 2,
            bbox={
                "boxstyle": "round,pad=0.35",
                "facecolor": "#20242A",
                "edgecolor": "#6B7280",
                "alpha": 0.9,
            },
        )

    def _draw_entry(
        self, entry: IdentifyPreviewEntry, data_axes_transform: transforms.Transform
    ) -> None:
        """Draw one preview entry when its wavelength bounds are valid."""
        lambda_min = entry.get("lambda_min")
        lambda_max = entry.get("lambda_max")
        if lambda_min is None or lambda_max is None:
            return

        try:
            start = float(lambda_min)
            end = float(lambda_max)
        except (TypeError, ValueError):
            return

        if not np.isfinite(start) or not np.isfinite(end):
            return
        if start == end:
            return

        center = entry.get("center")
        color = str(entry.get("color", "#0066CC"))
        fill_alpha = float(entry.get("fill_alpha", 0.08))
        line_alpha = float(entry.get("line_alpha", 0.85))
        line_width = float(entry.get("line_width", 1.0))
        line_style = str(entry.get("line_style", "--"))
        is_primary = bool(entry.get("is_primary", False))
        label = entry.get("label")

        base_zorder = self.span_zorder_base + (1 if is_primary else 0)

        span = self.axes.axvspan(start, end, color=color, alpha=fill_alpha, zorder=base_zorder - 1)
        self.spans.append(span)

        rect = patches.Rectangle(
            (start, 0.0),
            end - start,
            1.0,
            linewidth=line_width,
            linestyle=line_style,
            edgecolor=color,
            facecolor="none",
            alpha=line_alpha,
            transform=data_axes_transform,
            zorder=base_zorder,
        )
        self.axes.add_patch(rect)
        self.patches_.append(rect)

        if center is not None and np.isfinite(center):
            center_line = self.axes.axvline(
                float(center),
                color=color,
                linestyle="-",
                linewidth=line_width + (0.3 if is_primary else 0.0),
                alpha=line_alpha,
                zorder=base_zorder + 0.25,
            )
            self.lines.append(center_line)

        if label:
            self._draw_label(
                label=str(label),
                x_position=float(center if center is not None else (start + end) / 2.0),
                color=color,
                base_zorder=base_zorder,
            )

    def _draw_label(self, label: str, x_position: float, color: str, base_zorder: float) -> None:
        """Draw one preview label above the span."""
        label_transform = transforms.blended_transform_factory(
            self.axes.transData, self.axes.transAxes
        )
        text = self.axes.text(
            x_position,
            self.label_y,
            label,
            color=color,
            fontsize=9,
            fontweight="normal",
            ha="center",
            va="bottom",
            transform=label_transform,
            alpha=1.0,
            zorder=base_zorder + 0.5,
        )
        self.labels.append(text)
