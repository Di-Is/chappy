"""Velocity origin line overlay support for Matplotlib spectrum plots."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.backend_bases import FigureCanvasBase
    from matplotlib.lines import Line2D


@dataclass
class VelocityOriginOverlay:
    """Maintain the velocity plot origin marker line."""

    axes: Axes
    canvas: FigureCanvasBase
    color: str = "#FF6B6B"
    linestyle: str = "--"
    alpha: float = 0.8
    linewidth: float = 1.5
    zorder: int = 10
    line: Line2D | None = field(default=None, init=False)

    def show(self, wavelength: float) -> None:
        """Create or replace the origin marker at the given wavelength."""
        self.hide()
        self.line = self.axes.axvline(
            x=wavelength,
            color=self.color,
            linestyle=self.linestyle,
            alpha=self.alpha,
            linewidth=self.linewidth,
            zorder=self.zorder,
        )
        self.canvas.draw_idle()

    def hide(self) -> None:
        """Remove the origin marker if it exists."""
        if self.line is None:
            return
        with contextlib.suppress(ValueError):
            self.line.remove()
        self.line = None
        self.canvas.draw_idle()

    def update(self, wavelength: float) -> None:
        """Move the existing origin marker without recreating it."""
        if self.line is None:
            return
        self.line.set_xdata([wavelength, wavelength])
        self.canvas.draw_idle()
