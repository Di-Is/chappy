"""Utilities for managing rectangle zoom overlays in Matplotlib plots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from matplotlib.patches import Rectangle

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.backend_bases import FigureCanvasBase

Coordinate = tuple[float, float]


@dataclass
class ZoomOverlayHandle:
    """Maintain the rectangle zoom overlay geometry and drawing lifecycle."""

    axes: Axes
    canvas: FigureCanvasBase
    edgecolor: str = "blue"
    facecolor: str = "blue"
    alpha: float = 0.2
    linestyle: str = "--"
    linewidth: float = 1.0
    patch: Rectangle | None = field(default=None, init=False)
    start: Coordinate | None = field(default=None, init=False)
    current: Coordinate | None = field(default=None, init=False)

    def update(self, start: Coordinate, current: Coordinate) -> None:
        """Create or update the overlay using the provided coordinates."""
        self.start = start
        self.current = current

        min_x = min(start[0], current[0])
        min_y = min(start[1], current[1])
        width = abs(current[0] - start[0])
        height = abs(current[1] - start[1])

        if self.patch is None:
            self.patch = Rectangle(
                (min_x, min_y),
                width,
                height,
                linewidth=self.linewidth,
                edgecolor=self.edgecolor,
                facecolor=self.facecolor,
                alpha=self.alpha,
                linestyle=self.linestyle,
            )
            self.axes.add_patch(self.patch)
        else:
            self.patch.set_x(min_x)
            self.patch.set_y(min_y)
            self.patch.set_width(width)
            self.patch.set_height(height)

        self.canvas.draw_idle()

    def clear(self) -> None:
        """Remove the overlay from the axes and reset the stored geometry."""
        if self.patch is None:
            return

        self.patch.remove()
        self.patch = None
        self.start = None
        self.current = None
        self.canvas.draw_idle()
