"""State controller for rectangle zoom interactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chappy.gui.protocols.intent_types import ZoomRectIntent
from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.gui.spectrum.interaction.support.snapshots import (
    active_interaction_id_for,
    build_snapshot_from_outcome,
)
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    InteractionId,
    InteractionOutcome,
    InteractionPhase,
    InteractionStateSnapshot,
    RectZoomBounds,
    RectZoomContext,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.spectrum.interaction.channels.rect_zoom.interaction_controller import (
        RectZoomInteractionController,
    )
    from chappy.gui.spectrum.interaction.support.contexts import SnapshotContext


class RectZoomStateController:
    """Coordinate rectangle zoom state transitions."""

    def __init__(
        self,
        *,
        snapshot_consumer: Callable[[InteractionStateSnapshot[SnapshotContext]], None],
        rect_zoom_interaction_controller: RectZoomInteractionController,
        zoom_intent_emitter: Callable[[ZoomRectIntent], None],
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the rectangle zoom state controller."""
        self._snapshot_consumer = snapshot_consumer
        self._rect_zoom_interaction_controller = rect_zoom_interaction_controller
        self._zoom_intent_emitter = zoom_intent_emitter
        self._logger = logger or logging.getLogger(__name__).getChild("rect_zoom")
        self._phase: InteractionPhase = InteractionPhase.IDLE
        self._active_interaction_id: InteractionId | None = None
        self._latest_snapshot: InteractionStateSnapshot[RectZoomContext] | None = None

    @property
    def phase(self) -> InteractionPhase:
        """Return the last observed interaction phase."""
        return self._phase

    def process_event(self, event: InteractionEvent) -> bool:
        """Process a rectangle zoom event."""
        if event.channel is not InteractionChannel.RECT_ZOOM:
            msg = f"Unsupported channel {event.channel} for controller {InteractionChannel.RECT_ZOOM}"
            raise InteractionStateError(msg)

        if event.kind is InteractionEventKind.RECT_ZOOM_BEGIN:
            return self._handle_begin(event)
        if event.kind is InteractionEventKind.RECT_ZOOM_UPDATE:
            return self._handle_update(event)
        if event.kind is InteractionEventKind.RECT_ZOOM_COMPLETE:
            return self._handle_complete(event)
        if event.kind is InteractionEventKind.RECT_ZOOM_CANCEL:
            return self.cancel_interaction(reason=None)

        msg = f"Unsupported rect zoom interaction event kind: {event.kind!r}"
        raise InteractionStateError(msg)

    def cancel_interaction(self, *, reason: str | None) -> bool:
        """Cancel an active rectangle zoom interaction."""
        if self._active_interaction_id is None:
            self._logger.debug("Cancellation skipped; no active interaction")
            return False

        outcome = self._rect_zoom_interaction_controller.cancel_drag(reason=reason)
        if outcome is None:
            self._logger.debug("Cancellation skipped; controller returned no outcome")
            return False

        self._apply_outcome(outcome)
        return True

    def _handle_begin(self, event: InteractionEvent) -> bool:
        """Handle a rectangle zoom begin event."""
        if self._active_interaction_id is not None:
            msg = "Interaction already active; begin event is invalid"
            raise InteractionStateError(msg)

        if event.position is None:
            msg = "Rectangle zoom begin requires a coordinate payload"
            raise InteractionStateError(msg)

        outcome = self._rect_zoom_interaction_controller.begin_drag(event.position)
        self._apply_outcome(outcome)
        return True

    def _handle_update(self, event: InteractionEvent) -> bool:
        """Handle a rectangle zoom update event."""
        if self._active_interaction_id is None:
            msg = "Rectangle zoom update requires an active interaction"
            raise InteractionStateError(msg)

        if event.position is None:
            msg = "Rectangle zoom update requires a coordinate payload"
            raise InteractionStateError(msg)

        outcome = self._rect_zoom_interaction_controller.update_drag(event.position)
        if outcome is None:
            return False

        self._apply_outcome(outcome)
        return True

    def _handle_complete(self, event: InteractionEvent) -> bool:
        """Handle a rectangle zoom complete event."""
        if self._active_interaction_id is None:
            msg = "Rectangle zoom completion requires an active interaction"
            raise InteractionStateError(msg)

        if event.position is None:
            self._logger.debug("Rectangle zoom completion missing coordinate; cancelling")
            return self.cancel_interaction(reason="missing-coordinate")

        outcome = self._rect_zoom_interaction_controller.complete_drag(event.position)
        if outcome is None:
            return False

        self._apply_outcome(outcome)
        return True

    def _apply_outcome(self, outcome: InteractionOutcome[RectZoomContext]) -> None:
        """Apply an outcome, emit a snapshot, and emit zoom intent when complete."""
        snapshot = build_snapshot_from_outcome(outcome)

        self._logger.debug(
            "snapshot-emitted",
            extra={
                "interaction_id": snapshot.interaction_id,
                "phase": snapshot.phase.value,
                "bounds": self._bounds_as_dict(snapshot.context.bounds)
                if snapshot.context
                else None,
            },
        )
        self._snapshot_consumer(snapshot)

        if outcome.phase is InteractionPhase.IDLE and outcome.context.bounds:
            intent = self._build_zoom_intent(outcome.context.bounds)
            self._logger.debug(
                "zoom-intent-emitted",
                extra={
                    "interaction_id": snapshot.interaction_id,
                    "min_wavelength": intent.min_wavelength,
                    "max_wavelength": intent.max_wavelength,
                },
            )
            self._zoom_intent_emitter(intent)

        self._latest_snapshot = snapshot
        self._phase = outcome.phase
        self._active_interaction_id = active_interaction_id_for(
            phase=outcome.phase, interaction_id=outcome.interaction_id
        )

    def _build_zoom_intent(self, bounds: RectZoomBounds) -> ZoomRectIntent:
        """Create a ZoomRectIntent from computed bounds."""
        return ZoomRectIntent(
            min_wavelength=bounds.min_wavelength,
            max_wavelength=bounds.max_wavelength,
            min_flux=bounds.min_flux,
            max_flux=bounds.max_flux,
        )

    def _bounds_as_dict(self, bounds: RectZoomBounds | None) -> dict[str, float] | None:
        """Return bounds as a serialisable dictionary for logging."""
        if bounds is None:
            return None
        return {
            "min_wavelength": bounds.min_wavelength,
            "max_wavelength": bounds.max_wavelength,
            "min_flux": bounds.min_flux,
            "max_flux": bounds.max_flux,
        }
