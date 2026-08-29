"""Mask selection overlay drawing support for Matplotlib spectrum plots."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from matplotlib import colors as mcolors
from matplotlib import transforms
from matplotlib.patches import Rectangle

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.backend_bases import FigureCanvasBase
    from matplotlib.text import Text


@dataclass
class MaskSelectionOverlay:
    """Maintain the temporary mask selection patch and preview label.

    Args:
        axes: Matplotlib axes that owns the overlay artists.
        canvas: Canvas used to schedule redraws.
        color: Base color used for the selection patch.
        patch_alpha: Opacity applied to the selection patch.
        patch_zorder: Draw order applied to the selection patch.
        label_color: Text color for the preview label.
        label_box_color: Background color for the preview label.
        label_box_alpha: Background opacity for the preview label.
        label_zorder: Draw order applied to the preview label.
    """

    axes: Axes
    canvas: FigureCanvasBase
    color: str
    patch_alpha: float = 0.30
    patch_zorder: int = 8
    label_color: str = "#ecf0f1"
    label_box_color: str = "#2c3e50"
    label_box_alpha: float = 0.8
    label_zorder: int = 15
    patch: Rectangle | None = field(default=None, init=False)
    preview: Text | None = field(default=None, init=False)

    def update(self, start: float, end: float) -> None:
        """Create or update the overlay using the provided wavelength bounds.

        Args:
            start: Starting wavelength of the current selection.
            end: Ending wavelength of the current selection.
        """
        self._render_patch(start, end)
        self._update_preview_text(start, end)

    def clear(self) -> None:
        """Remove the temporary patch and preview label from the axes."""
        self._clear_patch()
        self._clear_preview()

    def _render_patch(self, start: float, end: float) -> None:
        """Create or update the shaded selection region.

        Args:
            start: Starting wavelength of the current selection.
            end: Ending wavelength of the current selection.
        """
        y_min, y_max = self.axes.get_ylim()
        left = min(start, end)
        width = abs(end - start)
        bottom = min(y_min, y_max)
        height = abs(y_max - y_min) or 1.0

        if self.patch is None:
            self.patch = Rectangle(
                (left, bottom),
                width,
                height,
                linewidth=0.0,
                edgecolor="none",
                facecolor=mcolors.to_rgba(self.color, alpha=self.patch_alpha),
                zorder=self.patch_zorder,
            )
            self.axes.add_patch(self.patch)
        else:
            self.patch.set_x(left)
            self.patch.set_width(width)
            self.patch.set_visible(True)

        if self.patch is None:
            return
        self.patch.set_y(bottom)
        self.patch.set_height(height)
        self.canvas.draw_idle()

    def _update_preview_text(self, start: float, end: float) -> None:
        """Update the mask selection preview label.

        Args:
            start: Starting wavelength of the current selection.
            end: Ending wavelength of the current selection.
        """
        center = (start + end) / 2.0
        width = abs(end - start)
        transform = transforms.blended_transform_factory(self.axes.transData, self.axes.transAxes)

        if self.preview is None:
            self.preview = self.axes.text(
                center,
                0.98,
                "",
                transform=transform,
                ha="center",
                va="top",
                color=self.label_color,
                fontsize=9,
                bbox={
                    "boxstyle": "round,pad=0.2",
                    "facecolor": self.label_box_color,
                    "edgecolor": "none",
                    "alpha": self.label_box_alpha,
                },
                zorder=self.label_zorder,
            )

        self.preview.set_transform(transform)
        self.preview.set_position((center, 0.98))
        self.preview.set_text(f"{start:.2f} – {end:.2f} Å\nΔλ {width:.2f} Å")
        self.preview.set_visible(True)
        self.canvas.draw_idle()

    def _clear_patch(self) -> None:
        """Remove the shaded selection region."""
        if self.patch is None:
            return
        with contextlib.suppress(ValueError):
            self.patch.remove()
        self.patch = None
        self.canvas.draw_idle()

    def _clear_preview(self) -> None:
        """Remove the preview label."""
        if self.preview is None:
            return
        with contextlib.suppress(ValueError):
            self.preview.remove()
        self.preview = None
        self.canvas.draw_idle()
