"""State controller for velocity activation interactions."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.gui.spectrum.interaction.support.snapshots import active_interaction_id_for
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    InteractionId,
    InteractionPhase,
    InteractionStateSnapshot,
    VelocityContext,
    VelocityInteractionPayload,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.channels.velocity.snapshot_emitter import (
        VelocitySnapshotEmitterPort,
    )


class VelocityStateController:
    """Coordinate velocity pending, activation, and cancellation transitions."""

    def __init__(
        self,
        *,
        velocity_snapshot_emitter: VelocitySnapshotEmitterPort,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialise the velocity state controller."""
        self._velocity_snapshot_emitter = velocity_snapshot_emitter
        self._logger = logger or logging.getLogger(__name__).getChild("velocity")
        self._phase: InteractionPhase = InteractionPhase.IDLE
        self._active_interaction_id: InteractionId | None = None
        self._latest_snapshot: InteractionStateSnapshot[VelocityContext] | None = None

    @property
    def phase(self) -> InteractionPhase:
        """Return the last observed interaction phase."""
        return self._phase

    def process_event(self, event: InteractionEvent) -> bool:
        """Process a velocity interaction event."""
        if event.channel is not InteractionChannel.VELOCITY:
            msg = (
                f"Unsupported channel {event.channel} for controller {InteractionChannel.VELOCITY}"
            )
            raise InteractionStateError(msg)

        if event.kind is InteractionEventKind.VELOCITY_PENDING:
            return self._handle_pending(event)
        if event.kind is InteractionEventKind.VELOCITY_COMMIT:
            return self._handle_commit(event)
        if event.kind is InteractionEventKind.VELOCITY_CANCEL:
            payload = (
                event.payload if isinstance(event.payload, VelocityInteractionPayload) else None
            )
            return self.cancel_interaction(
                reason=payload.reason if payload else None,
                trigger=payload.trigger if payload else None,
                modifiers=event.modifiers,
            )

        msg = f"Unsupported velocity interaction event kind: {event.kind!r}"
        raise InteractionStateError(msg)

    def cancel_interaction(
        self, *, reason: str | None, trigger: str | None = None, modifiers: int | None = None
    ) -> bool:
        """Cancel an active velocity interaction."""
        if self._active_interaction_id is None:
            self._logger.debug("Cancellation skipped; no active velocity interaction")
            return False

        previous_context = self._require_current_context()
        context = VelocityContext(
            target_wavelength=previous_context.target_wavelength,
            confirmed_wavelength=None,
            trigger=trigger or previous_context.trigger,
            modifiers=modifiers,
            cancel_reason=reason,
        )
        interaction_id = self._active_interaction_id
        self._emit_snapshot(
            interaction_id=interaction_id, phase=InteractionPhase.CANCELLED, context=context
        )
        return True

    def _handle_pending(self, event: InteractionEvent) -> bool:
        """Handle a velocity pending request."""
        if self._active_interaction_id is not None:
            self._logger.debug("Velocity pending request ignored; interaction already active")
            return False

        trigger = (
            event.payload.trigger
            if isinstance(event.payload, VelocityInteractionPayload)
            else None
        )
        context = VelocityContext(
            target_wavelength=self._extract_wavelength(event.position),
            confirmed_wavelength=None,
            trigger=trigger,
            modifiers=event.modifiers,
            cancel_reason=None,
        )
        self._emit_snapshot(
            interaction_id=self._new_interaction_id(),
            phase=InteractionPhase.ARMED,
            context=context,
        )
        return True

    def _handle_commit(self, event: InteractionEvent) -> bool:
        """Handle velocity activation from an active pending interaction."""
        if self._active_interaction_id is None:
            msg = "Velocity commit requires an active interaction"
            raise InteractionStateError(msg)

        confirmed_wavelength = self._extract_wavelength(event.position)
        if confirmed_wavelength is None:
            msg = "Velocity commit requires a confirmed wavelength"
            raise ValueError(msg)

        previous_context = self._require_current_context()
        trigger = (
            event.payload.trigger
            if isinstance(event.payload, VelocityInteractionPayload)
            else None
        )
        context = VelocityContext(
            target_wavelength=previous_context.target_wavelength,
            confirmed_wavelength=confirmed_wavelength,
            trigger=trigger or previous_context.trigger,
            modifiers=event.modifiers,
            cancel_reason=None,
        )
        interaction_id = self._active_interaction_id
        self._emit_snapshot(
            interaction_id=interaction_id, phase=InteractionPhase.IDLE, context=context
        )
        return True

    def _emit_snapshot(
        self, *, interaction_id: InteractionId, phase: InteractionPhase, context: VelocityContext
    ) -> None:
        """Emit a velocity snapshot through the configured emitter."""
        snapshot = InteractionStateSnapshot(
            interaction_id=interaction_id,
            channel=InteractionChannel.VELOCITY,
            phase=phase,
            context=context,
        )
        self._velocity_snapshot_emitter.emit(snapshot)
        self._latest_snapshot = snapshot
        self._phase = phase
        self._active_interaction_id = active_interaction_id_for(
            phase=phase, interaction_id=interaction_id
        )

    def _require_current_context(self) -> VelocityContext:
        """Return the active velocity context or raise on invariant mismatch."""
        snapshot = self._latest_snapshot
        if snapshot and snapshot.channel is InteractionChannel.VELOCITY:
            context = snapshot.context
            if context is None:
                msg = "Active velocity interaction requires a context"
                raise InteractionStateError(msg)
            if isinstance(context, VelocityContext):
                return context
            msg = f"Velocity snapshot context type mismatch: {type(context).__name__}"
            raise InteractionStateError(msg)
        msg = "Active velocity interaction requires a velocity snapshot"
        raise InteractionStateError(msg)

    @staticmethod
    def _new_interaction_id() -> InteractionId:
        """Create a new interaction identifier."""
        return InteractionId(uuid.uuid4().hex)

    @staticmethod
    def _extract_wavelength(position: tuple[float, float] | None) -> float | None:
        """Extract wavelength from an optional coordinate pair."""
        if position is None:
            return None
        return float(position[0])
