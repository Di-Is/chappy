"""Plot coordinate transformation utilities.

This module provides utilities for converting between Qt widget coordinates
and plot data coordinates for the spectrum plotting system.
"""
# mypy: disable-error-code="union-attr"

from __future__ import annotations

import logging
from collections.abc import Sequence  # noqa: TC003 - Runtime protocol annotations need it.
from typing import Protocol

logger = logging.getLogger(__name__)


class CanvasCoordinateSurface(Protocol):
    """Canvas surface required for coordinate conversion."""

    def devicePixelRatio(self) -> float:  # noqa: N802 - Qt API
        """Return the device pixel ratio."""
        ...

    def height(self) -> int:
        """Return the canvas height."""
        ...

    def width(self) -> int:
        """Return the canvas width."""
        ...


class DataCoordinateTransform(Protocol):
    """Matplotlib-like transform that converts display to data coordinates."""

    def transform(self, position: tuple[float, float]) -> Sequence[float]:
        """Transform a display coordinate into data coordinates."""
        ...


class InvertibleDataTransform(Protocol):
    """Matplotlib-like transform source exposing an inverted transform."""

    def inverted(self) -> DataCoordinateTransform:
        """Return the inverted transform."""
        ...


class CoordinateAxes(Protocol):
    """Axes surface required by coordinate conversion."""

    transData: InvertibleDataTransform  # noqa: N815 - Matplotlib API


class CoordinateRenderer(Protocol):
    """Renderer surface required by coordinate conversion."""

    axes: CoordinateAxes | None


class CoordinateTransformPlotWidget(Protocol):
    """Plot widget surface required by PlotCoordinateTransform."""

    canvas: CanvasCoordinateSurface
    renderer: CoordinateRenderer


class PlotCoordinateTransform:
    """Utility class for coordinate transformations between Qt and plot data coordinates.

    This class handles the complex coordinate system conversions needed when
    translating Qt widget mouse events to plot data coordinates.
    """

    def __init__(self, plot_widget: CoordinateTransformPlotWidget) -> None:
        """Initialize coordinate transformer.

        Args:
            plot_widget: The matplotlib plot widget
        """
        self.plot_widget = plot_widget

    def qt_to_data_coordinates(self, qt_x: float, qt_y: float) -> tuple[float, float]:
        """Convert Qt widget coordinates to plot data coordinates.

        Args:
            qt_x: X coordinate in Qt widget coordinates (pixels from top-left)
            qt_y: Y coordinate in Qt widget coordinates (pixels from top-left)

        Returns:
            Tuple of (data_x, data_y) in plot data units

        Raises:
            ValueError: If coordinate transformation fails
        """
        try:
            # Get canvas and axes
            canvas = self.plot_widget.canvas
            axes = self._require_axes()

            # Get DPI scaling factor
            dpi_ratio = canvas.devicePixelRatio()

            # Scale coordinates for high DPI displays
            scaled_x = qt_x * dpi_ratio
            scaled_y = qt_y * dpi_ratio

            # Convert Qt coordinates (top-left origin) to matplotlib display coordinates (bottom-left origin)
            canvas_height_physical = canvas.height() * dpi_ratio
            display_x = scaled_x
            display_y = canvas_height_physical - scaled_y  # Flip Y coordinate

            # Convert display coordinates to data coordinates using matplotlib transformation
            inv_transform = axes.transData.inverted()
            data_x, data_y = inv_transform.transform((display_x, display_y))

            return float(data_x), float(data_y)

        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            logger.warning("Failed to convert Qt coordinates to data coordinates: %s", e)
            # Return fallback coordinates
            msg = f"Coordinate transformation failed: {e}"
            raise ValueError(msg) from e

    def _require_axes(self) -> CoordinateAxes:
        """Return renderer axes or raise when the plot widget is not fully attached."""
        axes = self.plot_widget.renderer.axes
        if axes is None:
            msg = "Plot renderer axes are required for coordinate transformation."
            raise ValueError(msg)
        return axes

    def is_valid_position(self, qt_x: float, qt_y: float) -> bool:
        """Check if Qt position is within valid plot area.

        Args:
            qt_x: X coordinate in Qt widget coordinates
            qt_y: Y coordinate in Qt widget coordinates

        Returns:
            True if position is valid for coordinate transformation
        """
        try:
            # Check if position is within canvas bounds
            canvas = self.plot_widget.canvas
            if qt_x < 0 or qt_y < 0 or qt_x > canvas.width() or qt_y > canvas.height():
                return False

            # Try coordinate transformation to verify validity
            self.qt_to_data_coordinates(qt_x, qt_y)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False
        else:
            return True
