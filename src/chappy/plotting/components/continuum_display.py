"""Owner for continuum curve and reference-line display."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from chappy.plotting.renderers.base_renderer import PlotType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    from chappy.plotting.renderers import PlotStyle


class ContinuumCurveRenderer(Protocol):
    """Renderer API required by continuum display ownership."""

    plot_items: dict[str, object]
    axes: ContinuumAxes

    def add_curve(
        self,
        name: str,
        x: NDArray[np.float64],
        y: NDArray[np.float64],
        plot_type: PlotType = PlotType.SPECTRUM,
        style: PlotStyle | None = None,
    ) -> object:
        """Add a curve to the plot."""
        ...

    def update_curve(
        self, name: str, x: NDArray[np.float64] | None = None, y: NDArray[np.float64] | None = None
    ) -> None:
        """Update an existing curve."""
        ...

    def remove_curve(self, name: str) -> None:
        """Remove an existing curve."""
        ...


class ContinuumCanvas(Protocol):
    """Canvas redraw API required by continuum display ownership."""

    def draw_idle(self) -> None:
        """Schedule a redraw."""
        ...


class ContinuumEditorDisplayPort(Protocol):
    """Continuum editor operations driven by continuum display ownership."""

    def set_display_active(self, active: bool) -> None:
        """Set whether the continuum display is active."""
        ...

    def set_points(self, points: list[tuple[float, float]]) -> None:
        """Replace visible continuum anchor points."""
        ...


class ContinuumReferenceLine(Protocol):
    """Tracked reference-line API required by continuum display ownership."""

    def remove(self) -> None:
        """Remove the line from the axes."""
        ...

    def set_xdata(self, x: tuple[float, float]) -> None:
        """Update line x positions."""
        ...

    def set_label(self, label: str) -> None:
        """Update line label."""
        ...


class ContinuumAxes(Protocol):
    """Axes API required by continuum display ownership."""

    def get_xlim(self) -> tuple[float, float]:
        """Return current x limits."""
        ...

    def axhline(
        self,
        *,
        y: float,
        color: str,
        linestyle: str,
        alpha: float,
        linewidth: float,
        zorder: int,
        label: str,
    ) -> ContinuumReferenceLine:
        """Add a horizontal line."""
        ...


class ContinuumStyleProvider(Protocol):
    """Style provider API required by continuum display ownership."""

    def get_plot_style(self, plot_type: PlotType) -> PlotStyle:
        """Return the plot style for a curve."""
        ...


@dataclass
class ContinuumDisplayOwner:
    """Own continuum curve, anchor, and reference-line display."""

    renderer: ContinuumCurveRenderer
    canvas: ContinuumCanvas
    continuum_editor: ContinuumEditorDisplayPort
    style_registry: ContinuumStyleProvider
    _reference_line: ContinuumReferenceLine | None = field(default=None, init=False)

    def set_data(
        self,
        *,
        wavelength: NDArray[np.float64],
        continuum_flux: NDArray[np.float64],
        anchor_points: list[tuple[float, float]],
    ) -> None:
        """Render continuum curve data and visible anchors."""
        has_curve = len(wavelength) > 0 and len(continuum_flux) > 0
        if has_curve:
            style = self.style_registry.get_plot_style(PlotType.CONTINUUM)
            if "continuum" in self.renderer.plot_items:
                self.renderer.update_curve("continuum", wavelength, continuum_flux)
            else:
                self.renderer.add_curve(
                    "continuum",
                    wavelength,
                    continuum_flux,
                    plot_type=PlotType.CONTINUUM,
                    style=style,
                )
        elif "continuum" in self.renderer.plot_items:
            self.renderer.remove_curve("continuum")

        self.continuum_editor.set_display_active(True)
        self.continuum_editor.set_points(anchor_points)
        logger.debug("Set %d continuum anchor points", len(anchor_points))
        self.canvas.draw_idle()

    def hide_display(self) -> None:
        """Remove continuum visuals while preserving stored continuum data."""
        if "continuum" in self.renderer.plot_items:
            self.renderer.remove_curve("continuum")

        self.continuum_editor.set_display_active(False)
        self.clear_reference_line()
        self.canvas.draw_idle()

    def update_preview(
        self, wavelength: NDArray[np.float64], preview_flux: NDArray[np.float64]
    ) -> None:
        """Update the visible continuum curve during a drag preview."""
        if "continuum" not in self.renderer.plot_items:
            return

        self.renderer.update_curve("continuum", wavelength, preview_flux)
        self.canvas.draw_idle()

    def clear_reference_line(self) -> None:
        """Remove the tracked continuum reference line if present."""
        if self._reference_line is None:
            return

        self._reference_line.remove()
        self._reference_line = None
        self.canvas.draw_idle()

    def ensure_reference_line(self, label: str) -> None:
        """Ensure the flux=1.0 reference line exists and tracks current x limits."""
        xlim = self.renderer.axes.get_xlim()
        if self._reference_line is not None:
            self._reference_line.set_xdata(xlim)
            self.canvas.draw_idle()
            return

        self._reference_line = self.renderer.axes.axhline(
            y=1.0, color="red", linestyle="--", alpha=0.5, linewidth=1.0, zorder=5, label=label
        )
        self._reference_line.set_xdata(xlim)
        self.canvas.draw_idle()
        logger.debug("Added continuum reference line at flux=1.0")

    def refresh_reference_label(self, label: str) -> None:
        """Refresh the label of the tracked reference line."""
        if self._reference_line is None:
            return

        self._reference_line.set_label(label)
        self.canvas.draw_idle()

    def reset_after_renderer_clear(self) -> None:
        """Reset tracked artists after the shared renderer clears all axes."""
        self._reference_line = None
