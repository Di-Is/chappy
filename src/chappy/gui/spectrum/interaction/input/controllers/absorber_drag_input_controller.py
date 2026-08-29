"""Input-side controller for absorber drag gestures."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    AbsorberDragPayload,
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.input.owner_ports import AbsorberDragInputOwnerPort

logger = logging.getLogger(__name__)


class AbsorberDragInputController:
    """Convert absorber drag input phases into interaction events."""

    def __init__(self, *, owner: AbsorberDragInputOwnerPort) -> None:
        """Initialize the controller."""
        self._owner = owner
        self._selected_line_absorbers: set[str] | None = None

    def set_selected_line_absorbers(self, absorber_ids: set[str] | None) -> None:
        """Set absorbers that are eligible for optimize-mode dragging."""
        self._selected_line_absorbers = absorber_ids
        logger.debug("Updated selected line absorbers: %s", absorber_ids)

    def can_start_absorber_drag(self) -> bool:
        """Return whether an absorber drag interaction can start."""
        return self._owner.can_start_absorber_drag()

    def active_absorber_drag_id(self) -> str | None:
        """Return the active absorber drag id, if any."""
        return self._owner.active_absorber_drag_id()

    def acquire_absorber_drag(self, absorber_id: str) -> None:
        """Acquire absorber drag channel ownership for an absorber."""
        self._owner.acquire_absorber_drag(absorber_id)

    def clear_absorber_drag(self) -> None:
        """Clear absorber drag channel ownership."""
        self._owner.clear_absorber_drag()

    def can_drag_absorber(self, absorber_id: str) -> bool:
        """Return whether an absorber can be dragged."""
        if not self.can_start_absorber_drag():
            return False

        if not self._owner.absorber_drag_enabled():
            return False

        selected_absorbers = self._selected_line_absorbers
        if selected_absorbers is None:
            logger.debug("Allowing drag in OPTIMIZE mode (selection unrestricted)")
            return True

        return absorber_id in selected_absorbers

    def begin_drag_at(self, *, position: tuple[float, float], modifiers: int) -> bool:
        """Begin an absorber drag at a data-space position."""
        wavelength, _ = position
        absorber_id = self._owner.absorber_at_wavelength(float(wavelength))
        if absorber_id is None or not self.can_drag_absorber(absorber_id):
            return False

        event = InteractionEvent(
            channel=InteractionChannel.ABSORBER_DRAG,
            kind=InteractionEventKind.ABSORBER_DRAG_BEGIN,
            position=position,
            modifiers=modifiers,
            payload=AbsorberDragPayload(absorber_id=absorber_id),
        )
        handled = self._owner.require_absorber_drag_controller().process_event(event)
        if not handled:
            msg = "Absorber drag begin was rejected after drag eligibility passed."
            raise InteractionStateError(msg)
        return True

    def update_drag_at(self, *, position: tuple[float, float], modifiers: int) -> bool:
        """Update the active absorber drag."""
        if self._owner.active_absorber_drag_id() is None:
            return False

        event = InteractionEvent(
            channel=InteractionChannel.ABSORBER_DRAG,
            kind=InteractionEventKind.ABSORBER_DRAG_UPDATE,
            position=position,
            modifiers=modifiers,
        )
        handled = self._owner.require_absorber_drag_controller().process_event(event)
        if not handled:
            msg = "Absorber drag update was rejected during an active drag."
            raise InteractionStateError(msg)
        return True

    def complete_drag_at(self, *, position: tuple[float, float], modifiers: int) -> bool:
        """Complete the active absorber drag."""
        if self._owner.active_absorber_drag_id() is None:
            return False

        event = InteractionEvent(
            channel=InteractionChannel.ABSORBER_DRAG,
            kind=InteractionEventKind.ABSORBER_DRAG_COMPLETE,
            position=position,
            modifiers=modifiers,
        )
        handled = self._owner.require_absorber_drag_controller().process_event(event)
        if not handled:
            msg = "Absorber drag completion was rejected during an active drag."
            raise InteractionStateError(msg)
        return True

    def cancel_active_drag(
        self,
        *,
        reason: str | None = None,
        position: tuple[float, float] | None = None,
        modifiers: int | None = None,
        raise_on_rejected: bool = False,
    ) -> bool:
        """Cancel the active absorber drag, if any."""
        if (
            self._owner.active_input_channel() is not InteractionChannel.ABSORBER_DRAG
            and self._owner.active_absorber_drag_id() is None
        ):
            return False

        event = InteractionEvent(
            channel=InteractionChannel.ABSORBER_DRAG,
            kind=InteractionEventKind.ABSORBER_DRAG_CANCEL,
            position=position,
            modifiers=modifiers,
            payload=AbsorberDragPayload(reason=reason),
        )
        handled = self._owner.require_absorber_drag_controller().process_event(event)
        if not handled:
            if raise_on_rejected:
                msg = "Absorber drag cancellation was rejected during an active drag."
                raise InteractionStateError(msg)
            self._owner.clear_absorber_drag()

        logger.debug(
            "Absorber drag cancel requested", extra={"reason": reason, "handled": handled}
        )
        return handled
