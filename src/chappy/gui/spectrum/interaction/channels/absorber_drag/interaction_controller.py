"""Absorber drag controller coordinating state transitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.interaction.interaction_contracts import (
    AbsorberDragContext,
    Coordinate,
    InteractionChannel,
    InteractionId,
    InteractionOutcome,
    InteractionPhase,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.support.logging import InteractionLogEmitter


class AbsorberDragInteractionController:
    """Manage absorber drag interactions and produce structured outcomes."""

    def __init__(self, *, log_emitter: InteractionLogEmitter) -> None:
        """Initialise the controller.

        Args:
            log_emitter: Structured logger used for phase transitions.
        """
        self._log_emitter = log_emitter
        self._active = False
        self._absorber_id: str | None = None
        self._start: Coordinate | None = None
        self._current: Coordinate | None = None
        self._modifiers: int | None = None
        self._interaction_id: InteractionId | None = None
        self._counter = 0

    def begin_drag(
        self, *, absorber_id: str, start: Coordinate, modifiers: int | None
    ) -> InteractionOutcome[AbsorberDragContext]:
        """Record the drag starting point and emit an armed outcome."""
        self._counter += 1
        interaction_id = InteractionId(f"absorber-drag-{self._counter}")
        self._interaction_id = interaction_id
        self._absorber_id = absorber_id
        self._start = start
        self._current = start
        self._modifiers = modifiers
        self._active = True

        payload = {"absorber_id": absorber_id, "start": list(start)}
        self._log_emitter.emit(InteractionPhase.ARMED, payload)

        context = AbsorberDragContext(
            absorber_id=absorber_id,
            start=start,
            current=start,
            end=None,
            modifiers=modifiers,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.ABSORBER_DRAG,
            phase=InteractionPhase.ARMED,
            context=context,
            interaction_id=interaction_id,
        )

    def update_drag(
        self, *, current: Coordinate, modifiers: int | None
    ) -> InteractionOutcome[AbsorberDragContext] | None:
        """Update the drag position and emit an active outcome."""
        if not self._active or self._interaction_id is None or self._absorber_id is None:
            return None

        self._current = current
        if modifiers is not None:
            self._modifiers = modifiers

        payload = {"absorber_id": self._absorber_id, "current": list(current)}
        if self._start is not None:
            payload["start"] = list(self._start)
        self._log_emitter.emit(InteractionPhase.ACTIVE, payload)

        context = AbsorberDragContext(
            absorber_id=self._absorber_id,
            start=self._start,
            current=current,
            end=None,
            modifiers=self._modifiers,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.ABSORBER_DRAG,
            phase=InteractionPhase.ACTIVE,
            context=context,
            interaction_id=self._interaction_id,
        )

    def complete_drag(
        self, *, end: Coordinate, modifiers: int | None
    ) -> InteractionOutcome[AbsorberDragContext] | None:
        """Complete the drag and emit an idle outcome."""
        if not self._active or self._interaction_id is None or self._absorber_id is None:
            return None

        if modifiers is not None:
            self._modifiers = modifiers

        payload = {"absorber_id": self._absorber_id, "end": list(end)}
        if self._start is not None:
            payload["start"] = list(self._start)
        self._log_emitter.emit(InteractionPhase.IDLE, payload)

        context = AbsorberDragContext(
            absorber_id=self._absorber_id,
            start=self._start,
            current=end,
            end=end,
            modifiers=self._modifiers,
            cancel_reason=None,
        )
        interaction_id = self._interaction_id
        self._reset_state()
        return InteractionOutcome(
            channel=InteractionChannel.ABSORBER_DRAG,
            phase=InteractionPhase.IDLE,
            context=context,
            interaction_id=interaction_id,
        )

    def cancel_drag(self, *, reason: str | None) -> InteractionOutcome[AbsorberDragContext] | None:
        """Cancel the drag and emit a cancelled outcome."""
        if self._interaction_id is None or self._absorber_id is None:
            return None

        payload: dict[str, object | None] = {"absorber_id": self._absorber_id, "reason": reason}
        if self._current is not None:
            payload["current"] = list(self._current)
        self._log_emitter.emit(InteractionPhase.CANCELLED, payload)

        context = AbsorberDragContext(
            absorber_id=self._absorber_id,
            start=self._start,
            current=self._current,
            end=None,
            modifiers=self._modifiers,
            cancel_reason=reason,
        )
        interaction_id = self._interaction_id
        self._reset_state()
        return InteractionOutcome(
            channel=InteractionChannel.ABSORBER_DRAG,
            phase=InteractionPhase.CANCELLED,
            context=context,
            interaction_id=interaction_id,
        )

    def _reset_state(self) -> None:
        """Reset controller state to idle values."""
        self._active = False
        self._absorber_id = None
        self._start = None
        self._current = None
        self._modifiers = None
        self._interaction_id = None
