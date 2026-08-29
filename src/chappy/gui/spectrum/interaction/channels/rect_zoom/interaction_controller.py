"""Rectangular zoom controller coordinating overlay updates and state snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.interaction.interaction_contracts import (
    Coordinate,
    InteractionChannel,
    InteractionId,
    InteractionOutcome,
    InteractionPhase,
    RectZoomBounds,
    RectZoomContext,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.protocols.interaction_overlay import RectZoomOverlayProtocol
    from chappy.gui.spectrum.interaction.support.logging import InteractionLogEmitter


class RectZoomInteractionController:
    """Manage rectangle zoom interactions and produce structured outcomes."""

    def __init__(
        self,
        *,
        overlay_provider: Callable[[], RectZoomOverlayProtocol | None],
        log_emitter: InteractionLogEmitter,
    ) -> None:
        """Initialise the controller.

        Args:
            overlay_provider: Callable returning the plot overlay implementation.
            log_emitter: Structured logger used for phase transitions.
        """
        self._overlay_provider = overlay_provider
        self._log_emitter = log_emitter
        self._active = False
        self._start: Coordinate | None = None
        self._current: Coordinate | None = None
        self._interaction_id: InteractionId | None = None
        self._counter = 0

    def begin_drag(self, start: Coordinate) -> InteractionOutcome[RectZoomContext]:
        """Record the drag starting point and emit an armed outcome."""
        self._counter += 1
        interaction_id = InteractionId(f"rect-zoom-{self._counter}")
        self._interaction_id = interaction_id
        self._start = start
        self._current = start
        self._active = True

        self._log_emitter.emit(InteractionPhase.ARMED, {"start": list(start)})

        context = RectZoomContext(start=start, current=start, end=None, bounds=None)
        return InteractionOutcome(
            channel=InteractionChannel.RECT_ZOOM,
            phase=InteractionPhase.ARMED,
            context=context,
            interaction_id=interaction_id,
        )

    def update_drag(self, current: Coordinate) -> InteractionOutcome[RectZoomContext] | None:
        """Update the drag position and emit an active outcome."""
        if not self._active or self._start is None or self._interaction_id is None:
            return None

        self._current = current
        bounds = self._build_bounds(self._start, current)
        self._draw_overlay(self._start, current)

        payload = {"start": list(self._start), "current": list(current)}
        self._log_emitter.emit(InteractionPhase.ACTIVE, payload)

        context = RectZoomContext(start=self._start, current=current, end=None, bounds=bounds)
        return InteractionOutcome(
            channel=InteractionChannel.RECT_ZOOM,
            phase=InteractionPhase.ACTIVE,
            context=context,
            interaction_id=self._interaction_id,
        )

    def complete_drag(self, end: Coordinate) -> InteractionOutcome[RectZoomContext] | None:
        """Complete the drag, clear overlays, and emit an idle outcome."""
        if not self._active or self._start is None or self._interaction_id is None:
            return None

        bounds = self._build_bounds(self._start, end)
        interaction_id = self._interaction_id
        self._draw_overlay(self._start, end)
        self._clear_overlay()

        payload = {
            "start": list(self._start),
            "end": list(end),
            "bounds": {
                "min_w": bounds.min_wavelength,
                "max_w": bounds.max_wavelength,
                "min_f": bounds.min_flux,
                "max_f": bounds.max_flux,
            },
        }
        self._log_emitter.emit(InteractionPhase.IDLE, payload)

        context = RectZoomContext(start=self._start, current=end, end=end, bounds=bounds)
        self._reset_state()

        return InteractionOutcome(
            channel=InteractionChannel.RECT_ZOOM,
            phase=InteractionPhase.IDLE,
            context=context,
            interaction_id=interaction_id,
        )

    def cancel_drag(self, reason: str | None = None) -> InteractionOutcome[RectZoomContext] | None:
        """Cancel the drag and emit a cancelled outcome."""
        if self._interaction_id is None:
            return None

        interaction_id = self._interaction_id
        self._clear_overlay()
        self._reset_state()

        payload = {"reason": reason} if reason else None
        self._log_emitter.emit(InteractionPhase.CANCELLED, payload)

        context = RectZoomContext(start=None, current=None, end=None, bounds=None)
        return InteractionOutcome(
            channel=InteractionChannel.RECT_ZOOM,
            phase=InteractionPhase.CANCELLED,
            context=context,
            interaction_id=interaction_id,
        )

    def _build_bounds(self, start: Coordinate, other: Coordinate) -> RectZoomBounds:
        """Return bounds covering the start and other coordinates."""
        min_wavelength = min(start[0], other[0])
        max_wavelength = max(start[0], other[0])
        min_flux = min(start[1], other[1])
        max_flux = max(start[1], other[1])
        return RectZoomBounds(
            min_wavelength=min_wavelength,
            max_wavelength=max_wavelength,
            min_flux=min_flux,
            max_flux=max_flux,
        )

    def _draw_overlay(self, start: Coordinate, current: Coordinate) -> None:
        """Draw the rectangle overlay when the provider is available."""
        overlay = self._overlay_provider()
        if overlay is None:
            return
        overlay.update_rect_zoom(start, current)

    def _clear_overlay(self) -> None:
        """Clear the rectangle overlay when the provider is available."""
        overlay = self._overlay_provider()
        if overlay is None:
            return
        overlay.clear_rect_zoom()

    def _reset_state(self) -> None:
        """Reset controller state to idle values."""
        self._active = False
        self._start = None
        self._current = None
        self._interaction_id = None
