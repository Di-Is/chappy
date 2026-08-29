"""State controller for mask selection interactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
    MaskSelectionBeginPayload,
    MaskSelectionContext,
    MaskSelectionPositionPayload,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.spectrum.interaction.channels.mask_selection.interaction_controller import (
        MaskSelectionInteractionController,
    )
    from chappy.gui.spectrum.interaction.support.contexts import SnapshotContext


class MaskSelectionStateController:
    """Coordinate mask selection state transitions."""

    def __init__(
        self,
        *,
        snapshot_consumer: Callable[[InteractionStateSnapshot[SnapshotContext]], None],
        mask_selection_interaction_controller: MaskSelectionInteractionController,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the mask selection state controller."""
        self._snapshot_consumer = snapshot_consumer
        self._mask_selection_interaction_controller = mask_selection_interaction_controller
        self._logger = logger or logging.getLogger(__name__).getChild("mask_selection")
        self._phase: InteractionPhase = InteractionPhase.IDLE
        self._active_interaction_id: InteractionId | None = None
        self._latest_snapshot: InteractionStateSnapshot[MaskSelectionContext] | None = None

    @property
    def phase(self) -> InteractionPhase:
        """Return the last observed interaction phase."""
        return self._phase

    def process_event(self, event: InteractionEvent) -> bool:
        """Process a mask selection event."""
        if event.channel is not InteractionChannel.MASK_SELECTION:
            msg = (
                f"Unsupported channel {event.channel} for controller "
                f"{InteractionChannel.MASK_SELECTION}"
            )
            raise InteractionStateError(msg)

        if event.kind is InteractionEventKind.MASK_SELECTION_BEGIN:
            return self._handle_begin(event)
        if event.kind is InteractionEventKind.MASK_SELECTION_UPDATE:
            return self._handle_update(event)
        if event.kind is InteractionEventKind.MASK_SELECTION_COMPLETE:
            return self._handle_complete(event)
        if event.kind is InteractionEventKind.MASK_SELECTION_CANCEL:
            return self.cancel_interaction(reason=None)

        msg = f"Unsupported mask selection interaction event kind: {event.kind!r}"
        raise InteractionStateError(msg)

    def cancel_interaction(self, *, reason: str | None) -> bool:
        """Cancel an active mask selection interaction."""
        outcome = self._mask_selection_interaction_controller.cancel_selection(reason=reason)
        if outcome is None:
            self._logger.debug("Cancellation skipped; no active mask selection")
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_begin(self, event: InteractionEvent) -> bool:
        """Handle a mask selection begin event."""
        if self._active_interaction_id is not None:
            msg = "Interaction already active; begin event is invalid"
            raise InteractionStateError(msg)

        if not isinstance(event.payload, MaskSelectionBeginPayload):
            msg = "Mask selection begin requires a begin payload"
            raise InteractionStateError(msg)

        outcome = self._mask_selection_interaction_controller.begin_selection(
            event.payload.start_pos,
            selection_mode=event.payload.selection_mode,
            mask_id=event.payload.mask_id,
            group_id=event.payload.group_id,
            initial_range=event.payload.initial_range,
            existing_mask=event.payload.existing_mask,
        )
        self._apply_outcome(outcome)
        return True

    def _handle_update(self, event: InteractionEvent) -> bool:
        """Handle a mask selection update event."""
        if self._active_interaction_id is None:
            msg = "Mask selection update requires an active interaction"
            raise InteractionStateError(msg)

        if not isinstance(event.payload, MaskSelectionPositionPayload):
            msg = "Mask selection update requires a position payload"
            raise InteractionStateError(msg)

        outcome = self._mask_selection_interaction_controller.update_selection(
            event.payload.position
        )
        if outcome is None:
            return False

        self._apply_outcome(outcome)
        return True

    def _handle_complete(self, event: InteractionEvent) -> bool:
        """Handle a mask selection completion event."""
        if self._active_interaction_id is None:
            msg = "Mask selection completion requires an active interaction"
            raise InteractionStateError(msg)

        if not isinstance(event.payload, MaskSelectionPositionPayload):
            msg = "Mask selection complete requires a position payload"
            raise InteractionStateError(msg)

        outcome = self._mask_selection_interaction_controller.complete_selection(
            event.payload.position
        )
        if outcome is None:
            return False

        self._apply_outcome(outcome)
        return True

    def _apply_outcome(self, outcome: InteractionOutcome[MaskSelectionContext]) -> None:
        """Apply mask selection outcome and emit a snapshot."""
        snapshot = build_snapshot_from_outcome(outcome)
        self._snapshot_consumer(snapshot)
        self._latest_snapshot = snapshot
        self._phase = outcome.phase
        self._active_interaction_id = active_interaction_id_for(
            phase=outcome.phase, interaction_id=outcome.interaction_id
        )
