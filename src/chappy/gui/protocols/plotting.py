"""Plot-related Protocol definitions for GUI module.

This module consolidates all plotting-related Protocol definitions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

PlotNumeric = float | int
PlotSequence = Sequence[PlotNumeric]
PlotKwargSequence = Sequence[PlotNumeric | str | bool | None]
PlotDataArgument = PlotNumeric | PlotSequence
PlotKwargValue = PlotNumeric | str | bool | None | PlotKwargSequence

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent


@runtime_checkable
class PlotWidgetProtocol(Protocol):
    """Protocol for plot widgets with common interface."""

    def plot(
        self,
        x: Sequence[float] | Sequence[tuple[float, float]] | None = None,
        y: Sequence[float] | None = None,
        **kwargs: PlotKwargValue,
    ) -> PlotItemProtocol | None:
        """Draw data on the plot widget.

        Args:
            x: Optional x values to plot.
            y: Optional y values to plot.
            **kwargs: Additional keyword options forwarded to the backend.

        Returns:
            Backend-specific result of the plot call.
        """
        ...

    def auto_range(self) -> None:
        """Automatically adjust the view range to fit current data."""
        ...

    def set_range(self, **kwargs: PlotKwargValue) -> None:
        """Manually set the view range using backend-specific keywords."""
        ...

    def setFocus(self) -> None:
        """Request keyboard focus for the widget."""
        ...


@runtime_checkable
class RendererProtocol(Protocol):
    """Protocol for plot renderers."""

    def auto_range(self) -> None:
        """Adjust renderer bounds to fit the displayed data."""
        ...

    def set_range(self, **kwargs: PlotKwargValue) -> None:
        """Apply a custom range to the renderer."""
        ...

    def get_range(self) -> tuple[float, float, float, float]:
        """Get the current visible range.

        Returns:
            Tuple of (x_min, x_max, y_min, y_max)
        """
        ...


@runtime_checkable
class PlotItemProtocol(Protocol):
    """Protocol for plot items."""

    def setVisible(self, visible: bool) -> None:
        """Control whether the plot item is shown.

        Args:
            visible: Whether the item should be displayed.
        """
        ...

    def isVisible(self) -> bool:
        """Report whether the plot item is currently visible."""
        ...

    def setData(self, *args: PlotDataArgument, **kwargs: PlotKwargValue) -> None:
        """Update the data shown by the plot item."""
        ...


@runtime_checkable
class SpectrumPlotWidget(Protocol):
    """Protocol for spectrum plot widgets."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle a key press occurring while the widget has focus.

        Args:
            event: Qt key event to process.
        """
        ...


@runtime_checkable
class ContinuumPlotWidget(Protocol):
    """Protocol for plot widgets with continuum editing capabilities.

    Continuum editing now uses interaction state snapshots and sends
    display data to the connected spectrum plot through this typed boundary.
    """

    def set_continuum_data(
        self, wavelength: object, flux: object, anchor_points: Sequence[tuple[float, float]]
    ) -> None:
        """Display continuum data and anchor points."""
        ...

    def hide_continuum_display(self) -> None:
        """Hide the continuum display on the plot."""
        ...
