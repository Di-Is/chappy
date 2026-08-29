"""Interaction overlay Protocol definitions for GUI module.

This module defines plot-widget contracts for temporary interaction overlays.
Each protocol represents one interaction family so callers depend only on the
overlay methods they actually need.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RectZoomOverlayProtocol(Protocol):
    """Protocol for plot widgets that render rectangle zoom overlays."""

    def update_rect_zoom(self, start: tuple[float, float], current: tuple[float, float]) -> None:
        """Update the rectangle zoom overlay.

        Args:
            start: Starting position in data coordinates.
            current: Current cursor position in data coordinates.
        """
        ...

    def clear_rect_zoom(self) -> None:
        """Clear the rectangle zoom overlay and redraw the plot."""
        ...


@runtime_checkable
class AbsorberDragBeginOverlayProtocol(Protocol):
    """Protocol for plot widgets that start absorber drag overlays."""

    def begin_absorber_drag(self, absorber_id: str, initial_wavelength: float) -> None:
        """Begin an absorber drag interaction.

        Args:
            absorber_id: Unique identifier for the absorber being dragged.
            initial_wavelength: Initial wavelength position of the absorber.
        """
        ...


@runtime_checkable
class AbsorberDragFinishOverlayProtocol(Protocol):
    """Protocol for plot widgets that finish absorber drag overlays."""

    def finish_absorber_drag(self, absorber_id: str) -> None:
        """Finish an absorber drag interaction and update the display.

        Args:
            absorber_id: Unique identifier for the absorber that was dragged.
        """
        ...


@runtime_checkable
class AbsorberDragUpdateOverlayProtocol(Protocol):
    """Protocol for plot widgets that update absorber drag overlays."""

    def update_dragging_absorber_position(self, component_id: str, new_wavelength: float) -> None:
        """Update the temporary absorber drag overlay position.

        Args:
            component_id: Unique identifier for the absorber being dragged.
            new_wavelength: Current wavelength position of the absorber.
        """
        ...


@runtime_checkable
class AbsorberDragOverlayProtocol(
    AbsorberDragBeginOverlayProtocol,
    AbsorberDragUpdateOverlayProtocol,
    AbsorberDragFinishOverlayProtocol,
    Protocol,
):
    """Protocol for plot widgets that render complete absorber drag overlays."""


@runtime_checkable
class MaskSelectionOverlayProtocol(Protocol):
    """Protocol for plot widgets that render mask selection overlays."""

    def begin_mask_selection(self, start: float) -> None:
        """Begin a mask selection overlay anchored at ``start``.

        Args:
            start: Starting wavelength for the mask selection.
        """
        ...

    def update_mask_selection(self, start: float, current: float) -> None:
        """Update the mask selection overlay.

        Args:
            start: Original starting wavelength of the selection.
            current: Current cursor wavelength during the drag.
        """
        ...

    def clear_mask_selection(self) -> None:
        """Clear any active mask selection overlay and redraw the plot."""
        ...


@runtime_checkable
class InteractionOverlayProtocol(
    RectZoomOverlayProtocol, AbsorberDragOverlayProtocol, MaskSelectionOverlayProtocol, Protocol
):
    """Protocol for plot widgets with all interaction overlay capabilities."""
