"""State controller for continuum editing interactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.gui.spectrum.interaction.support.snapshots import (
    active_interaction_id_for,
    build_snapshot_from_outcome,
)
from chappy.presentation.interaction.interaction_contracts import (
    ContinuumContext,
    ContinuumPointPayload,
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    InteractionId,
    InteractionOutcome,
    InteractionPhase,
    InteractionStateSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.modes.continuum.controllers.interaction_controller import (
        ContinuumInteractionController,
    )
    from chappy.gui.spectrum.interaction.support.contexts import SnapshotContext


class ContinuumStateController:
    """Coordinate continuum editing state transitions."""

    def __init__(
        self,
        *,
        snapshot_consumer: Callable[[InteractionStateSnapshot[SnapshotContext]], None],
        continuum_interaction_controller: ContinuumInteractionController,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the continuum state controller."""
        self._snapshot_consumer = snapshot_consumer
        self._continuum_interaction_controller = continuum_interaction_controller
        self._logger = logger or logging.getLogger(__name__).getChild("continuum")
        self._phase: InteractionPhase = InteractionPhase.IDLE
        self._active_interaction_id: InteractionId | None = None
        self._latest_snapshot: InteractionStateSnapshot[ContinuumContext] | None = None

    @property
    def phase(self) -> InteractionPhase:
        """Return the last observed interaction phase."""
        return self._phase

    def process_event(self, event: InteractionEvent) -> bool:  # noqa: PLR0911
        """Process a continuum editing event."""
        if event.channel is not InteractionChannel.CONTINUUM:
            msg = (
                f"Unsupported channel {event.channel} for controller "
                f"{InteractionChannel.CONTINUUM}"
            )
            raise InteractionStateError(msg)

        if event.kind is InteractionEventKind.CONTINUUM_ADD_BEGIN:
            return self._handle_add_begin(event)
        if event.kind is InteractionEventKind.CONTINUUM_MOVE_BEGIN:
            return self._handle_move_begin(event)
        if event.kind is InteractionEventKind.CONTINUUM_MOVE_UPDATE:
            return self._handle_move_update(event)
        if event.kind is InteractionEventKind.CONTINUUM_MOVE_COMPLETE:
            return self._handle_move_complete(event)
        if event.kind is InteractionEventKind.CONTINUUM_ADD_COMPLETE:
            return self._handle_add_complete(event)
        if event.kind is InteractionEventKind.CONTINUUM_DELETE_BEGIN:
            return self._handle_delete_begin(event)
        if event.kind is InteractionEventKind.CONTINUUM_DELETE_COMPLETE:
            return self._handle_delete_complete()
        if event.kind is InteractionEventKind.CONTINUUM_SELECT:
            return self._handle_select(event)
        if event.kind is InteractionEventKind.CONTINUUM_CANCEL:
            return self.cancel_interaction(reason=None)

        msg = f"Unsupported continuum interaction event kind: {event.kind!r}"
        raise InteractionStateError(msg)

    def cancel_interaction(self, *, reason: str | None) -> bool:
        """Cancel an active continuum interaction."""
        outcome = self._continuum_interaction_controller.cancel(reason=reason)
        if outcome is None:
            self._logger.debug("Cancellation skipped; no active continuum operation")
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_add_begin(self, event: InteractionEvent) -> bool:
        """Handle a continuum add begin event."""
        if event.position is None:
            msg = "Continuum add begin requires a position"
            raise InteractionStateError(msg)

        outcome = self._continuum_interaction_controller.begin_add(event.position)
        self._apply_outcome(outcome)

        if outcome.phase is InteractionPhase.ARMED:
            complete_outcome = self._continuum_interaction_controller.complete(event.position)
            if complete_outcome is not None:
                self._apply_outcome(complete_outcome)

        return True

    def _handle_move_begin(self, event: InteractionEvent) -> bool:
        """Handle a continuum move begin event."""
        if event.position is None:
            msg = "Continuum move begin requires a position"
            raise InteractionStateError(msg)

        if not isinstance(event.payload, ContinuumPointPayload):
            msg = "Continuum move begin requires a point payload"
            raise InteractionStateError(msg)

        if event.payload.point_index is None:
            msg = "Continuum move begin requires point_index in payload"
            raise InteractionStateError(msg)

        outcome = self._continuum_interaction_controller.begin_move(
            event.payload.point_index, event.position
        )
        if outcome is None:
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_move_update(self, event: InteractionEvent) -> bool:
        """Handle a continuum move update event."""
        if event.position is None:
            msg = "Continuum move update requires a position"
            raise InteractionStateError(msg)

        outcome = self._continuum_interaction_controller.update(event.position)
        if outcome is None:
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_move_complete(self, event: InteractionEvent) -> bool:
        """Handle a continuum move complete event."""
        outcome = self._continuum_interaction_controller.complete(event.position)
        if outcome is None:
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_add_complete(self, event: InteractionEvent) -> bool:
        """Handle a continuum add complete event."""
        outcome = self._continuum_interaction_controller.complete(event.position)
        if outcome is None:
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_delete_begin(self, event: InteractionEvent) -> bool:
        """Handle a continuum delete begin event."""
        if not isinstance(event.payload, ContinuumPointPayload):
            msg = "Continuum delete begin requires a point payload"
            raise InteractionStateError(msg)

        if event.payload.point_index is None:
            msg = "Continuum delete begin requires point_index in payload"
            raise InteractionStateError(msg)

        outcome = self._continuum_interaction_controller.begin_delete(event.payload.point_index)
        if outcome is None:
            return False
        self._apply_outcome(outcome)

        if outcome.phase is InteractionPhase.ARMED:
            complete_outcome = self._continuum_interaction_controller.complete(None)
            if complete_outcome is not None:
                self._apply_outcome(complete_outcome)

        return True

    def _handle_delete_complete(self) -> bool:
        """Handle a continuum delete complete event."""
        outcome = self._continuum_interaction_controller.complete(None)
        if outcome is None:
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_select(self, event: InteractionEvent) -> bool:
        """Handle a continuum select event."""
        point_index: int | None = None
        if isinstance(event.payload, ContinuumPointPayload):
            point_index = event.payload.point_index

        outcome = self._continuum_interaction_controller.begin_select(point_index)
        if outcome is None:
            return False
        self._apply_outcome(outcome)
        return True

    def _apply_outcome(self, outcome: InteractionOutcome[ContinuumContext]) -> None:
        """Apply continuum editing outcome and emit a snapshot."""
        snapshot = build_snapshot_from_outcome(outcome)
        self._snapshot_consumer(snapshot)
        self._latest_snapshot = snapshot
        self._phase = outcome.phase
        self._active_interaction_id = active_interaction_id_for(
            phase=outcome.phase, interaction_id=outcome.interaction_id
        )
