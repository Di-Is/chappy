"""State controller for absorber drag interactions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chappy.gui.protocols.intent_types import (
    EndAbsorberDragIntent,
    StartAbsorberDragIntent,
    UpdateAbsorberDragIntent,
)
from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.gui.spectrum.interaction.support.snapshots import (
    active_interaction_id_for,
    build_snapshot_from_outcome,
)
from chappy.presentation.interaction.interaction_contracts import (
    AbsorberDragContext,
    AbsorberDragPayload,
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

    from chappy.gui.spectrum.interaction.channels.absorber_drag.interaction_controller import (
        AbsorberDragInteractionController,
    )
    from chappy.gui.spectrum.interaction.support.contexts import SnapshotContext

type AbsorberDragIntent = (
    StartAbsorberDragIntent | UpdateAbsorberDragIntent | EndAbsorberDragIntent
)


class AbsorberDragStateController:
    """Coordinate absorber drag state transitions."""

    def __init__(
        self,
        *,
        snapshot_consumer: Callable[[InteractionStateSnapshot[SnapshotContext]], None],
        absorber_drag_interaction_controller: AbsorberDragInteractionController,
        absorber_drag_intent_emitter: Callable[[AbsorberDragIntent], None],
        absorber_drag_state_tracker: Callable[[str | None], None],
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the absorber drag state controller."""
        self._snapshot_consumer = snapshot_consumer
        self._absorber_drag_interaction_controller = absorber_drag_interaction_controller
        self._absorber_drag_intent_emitter = absorber_drag_intent_emitter
        self._absorber_drag_state_tracker = absorber_drag_state_tracker
        self._logger = logger or logging.getLogger(__name__).getChild("absorber_drag")
        self._phase: InteractionPhase = InteractionPhase.IDLE
        self._active_interaction_id: InteractionId | None = None
        self._latest_snapshot: InteractionStateSnapshot[AbsorberDragContext] | None = None

    @property
    def phase(self) -> InteractionPhase:
        """Return the last observed interaction phase."""
        return self._phase

    def process_event(self, event: InteractionEvent) -> bool:
        """Process an absorber drag event."""
        if event.channel is not InteractionChannel.ABSORBER_DRAG:
            msg = (
                f"Unsupported channel {event.channel} for controller "
                f"{InteractionChannel.ABSORBER_DRAG}"
            )
            raise InteractionStateError(msg)

        if event.kind is InteractionEventKind.ABSORBER_DRAG_BEGIN:
            return self._handle_begin(event)
        if event.kind is InteractionEventKind.ABSORBER_DRAG_UPDATE:
            return self._handle_update(event)
        if event.kind is InteractionEventKind.ABSORBER_DRAG_COMPLETE:
            return self._handle_complete(event)
        if event.kind is InteractionEventKind.ABSORBER_DRAG_CANCEL:
            reason = (
                event.payload.reason if isinstance(event.payload, AbsorberDragPayload) else None
            )
            return self.cancel_interaction(reason=reason)

        msg = f"Unsupported absorber drag interaction event kind: {event.kind!r}"
        raise InteractionStateError(msg)

    def cancel_interaction(self, *, reason: str | None) -> bool:
        """Cancel an active absorber drag interaction."""
        if self._active_interaction_id is None:
            self._logger.debug("Cancellation skipped; no active interaction")
            return False

        outcome = self._absorber_drag_interaction_controller.cancel_drag(reason=reason)
        if outcome is None:
            self._logger.debug("Cancellation skipped; no active absorber drag")
            return False
        self._apply_outcome(outcome)
        return True

    def _handle_begin(self, event: InteractionEvent) -> bool:
        """Handle absorber drag begin events and emit armed outcomes."""
        if self._active_interaction_id is not None:
            msg = "Interaction already active; begin event is invalid"
            raise InteractionStateError(msg)

        if not isinstance(event.payload, AbsorberDragPayload):
            msg = "Absorber drag begin requires an absorber payload"
            raise InteractionStateError(msg)

        if event.payload.absorber_id is None:
            msg = "Absorber drag begin requires an absorber identifier"
            raise InteractionStateError(msg)

        if event.position is None:
            msg = "Absorber drag begin requires a coordinate payload"
            raise InteractionStateError(msg)

        outcome = self._absorber_drag_interaction_controller.begin_drag(
            absorber_id=event.payload.absorber_id, start=event.position, modifiers=event.modifiers
        )
        self._apply_outcome(outcome)
        return True

    def _handle_update(self, event: InteractionEvent) -> bool:
        """Handle absorber drag update events during active interactions."""
        if self._active_interaction_id is None:
            msg = "Absorber drag update requires an active interaction"
            raise InteractionStateError(msg)

        if event.position is None:
            msg = "Absorber drag update requires a coordinate payload"
            raise InteractionStateError(msg)

        outcome = self._absorber_drag_interaction_controller.update_drag(
            current=event.position, modifiers=event.modifiers
        )
        if outcome is None:
            return False

        self._apply_outcome(outcome)
        return True

    def _handle_complete(self, event: InteractionEvent) -> bool:
        """Handle absorber drag completion events and emit final outcomes."""
        if self._active_interaction_id is None:
            msg = "Absorber drag completion requires an active interaction"
            raise InteractionStateError(msg)

        if event.position is None:
            reason = (
                event.payload.reason
                if isinstance(event.payload, AbsorberDragPayload)
                else "missing-coordinate"
            )
            outcome = self._absorber_drag_interaction_controller.cancel_drag(reason=reason)
            if outcome is None:
                return False
            self._apply_outcome(outcome)
            return True

        outcome = self._absorber_drag_interaction_controller.complete_drag(
            end=event.position, modifiers=event.modifiers
        )
        if outcome is None:
            return False

        self._apply_outcome(outcome)
        return True

    def _apply_outcome(self, outcome: InteractionOutcome[AbsorberDragContext]) -> None:
        """Apply absorber drag outcomes and update cached snapshot state."""
        snapshot = build_snapshot_from_outcome(outcome)
        self._snapshot_consumer(snapshot)
        self._update_drag_state(snapshot)
        self._emit_drag_intent(outcome)
        self._latest_snapshot = snapshot
        self._phase = outcome.phase
        self._active_interaction_id = active_interaction_id_for(
            phase=outcome.phase, interaction_id=outcome.interaction_id
        )

    def _update_drag_state(self, snapshot: InteractionStateSnapshot[AbsorberDragContext]) -> None:
        """Update the external absorber drag state tracker."""
        context = snapshot.context
        if context is None or snapshot.phase in (
            InteractionPhase.IDLE,
            InteractionPhase.CANCELLED,
        ):
            self._absorber_drag_state_tracker(None)
            return
        self._absorber_drag_state_tracker(context.absorber_id)

    def _emit_drag_intent(self, outcome: InteractionOutcome[AbsorberDragContext]) -> None:
        """Emit absorber drag intents corresponding to state outcomes."""
        context = outcome.context
        if outcome.phase is InteractionPhase.ARMED:
            if context.absorber_id is None or context.start is None:
                msg = "Absorber drag begin requires an absorber id and start position"
                raise InteractionStateError(msg)
            self._absorber_drag_intent_emitter(
                StartAbsorberDragIntent(
                    absorber_id=context.absorber_id,
                    initial_wavelength=context.start[0],
                    initial_position=context.start,
                    wavelength_already_converted=True,
                )
            )
            return

        if outcome.phase is InteractionPhase.ACTIVE:
            if context.absorber_id is None or context.current is None:
                msg = "Absorber drag update requires an absorber id and current position"
                raise InteractionStateError(msg)
            self._absorber_drag_intent_emitter(
                UpdateAbsorberDragIntent(
                    absorber_id=context.absorber_id, current_wavelength=context.current[0]
                )
            )
            return

        if outcome.phase is InteractionPhase.IDLE:
            if context.absorber_id is None or context.end is None:
                msg = "Absorber drag completion requires an absorber id and end position"
                raise InteractionStateError(msg)
            self._absorber_drag_intent_emitter(
                EndAbsorberDragIntent(
                    absorber_id=context.absorber_id,
                    final_wavelength=context.end[0],
                    calculate_redshift=True,
                )
            )
