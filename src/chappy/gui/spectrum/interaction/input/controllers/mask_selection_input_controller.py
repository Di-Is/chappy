"""Input-side controller for mask selection gestures."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
    MaskSelectionPositionPayload,
    MaskSelectionRequest,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.input.owner_ports import MaskSelectionInputOwnerPort

logger = logging.getLogger(__name__)


class MaskSelectionInputController:
    """Convert mask selection input phases into interaction events."""

    def __init__(self, *, owner: MaskSelectionInputOwnerPort) -> None:
        """Initialize the controller."""
        self._owner = owner
        self._request: MaskSelectionRequest | None = None
        self._active = False

    @property
    def active(self) -> bool:
        """Return whether a mask selection drag is active."""
        return self._active

    def begin_interaction(self, request: MaskSelectionRequest) -> bool:
        """Prime the mask selection controller using the provided request."""
        controller = self._owner.require_mask_selection_controller()

        if not self._owner.can_start_mask_selection():
            logger.warning(
                "Mask selection ignored because channel %s is active",
                self._owner.active_input_channel(),
            )
            return False

        self._request = request
        self._owner.acquire_mask_selection()
        self._active = False
        self._owner.set_mask_selection_cursor(True)

        initial_range = request.initial_range
        if initial_range is None:
            return True

        start_hint, end_hint = initial_range
        begin_event = InteractionEvent(
            channel=InteractionChannel.MASK_SELECTION,
            kind=InteractionEventKind.MASK_SELECTION_BEGIN,
            payload=request.build_begin_payload(start_hint),
        )
        handled = controller.process_event(begin_event)
        if not handled:
            self.reset()
            return False

        update_event = InteractionEvent(
            channel=InteractionChannel.MASK_SELECTION,
            kind=InteractionEventKind.MASK_SELECTION_UPDATE,
            payload=request.build_update_payload(end_hint),
        )
        handled = controller.process_event(update_event)
        if not handled:
            self.reset()
            msg = "Mask selection initial range update was rejected after begin succeeded."
            raise InteractionStateError(msg)
        self._active = True
        return True

    def cancel_interaction(self, *, reason: str | None = None) -> bool:
        """Cancel the active mask selection interaction if present."""
        controller = self._owner.require_mask_selection_controller()

        handled = controller.cancel_interaction(reason=reason)
        self.reset()
        return handled

    def reset(self) -> None:
        """Clear mask selection tracking fields."""
        self._request = None
        self._active = False
        self._owner.clear_mask_selection()
        self._owner.set_mask_selection_cursor(False)

    def update_active_selection(self, *, wavelength: float) -> bool:
        """Update an active mask selection drag."""
        if not self._active:
            return False

        controller = self._owner.require_mask_selection_controller()
        update_event = InteractionEvent(
            channel=InteractionChannel.MASK_SELECTION,
            kind=InteractionEventKind.MASK_SELECTION_UPDATE,
            payload=MaskSelectionPositionPayload(position=wavelength),
        )
        handled = controller.process_event(update_event)
        if not handled:
            msg = "Mask selection update was rejected during an active selection."
            raise InteractionStateError(msg)
        return True

    def begin_drag_at(self, *, wavelength: float) -> bool:
        """Begin the interactive mask selection drag at a wavelength."""
        controller = self._owner.require_mask_selection_controller()

        if self._active:
            return True

        request = self._request
        if request is None:
            request = MaskSelectionRequest(
                selection_mode="create",
                group_id=None,
                mask_id=None,
                initial_range=None,
                existing_mask=None,
            )
            self._request = request

        begin_event = InteractionEvent(
            channel=InteractionChannel.MASK_SELECTION,
            kind=InteractionEventKind.MASK_SELECTION_BEGIN,
            payload=request.build_begin_payload(wavelength),
        )
        handled = controller.process_event(begin_event)
        if handled:
            self._active = True
            return True

        self.reset()
        msg = "Mask selection begin was rejected after selection activation."
        raise InteractionStateError(msg)

    def complete_drag_at(self, *, wavelength: float) -> bool:
        """Complete the active mask selection drag at a wavelength."""
        controller = self._owner.require_mask_selection_controller()

        if not self._active:
            return True

        request = self._request
        if request is None:
            msg = "Mask selection completion requires an active selection request."
            raise RuntimeError(msg)

        complete_event = InteractionEvent(
            channel=InteractionChannel.MASK_SELECTION,
            kind=InteractionEventKind.MASK_SELECTION_COMPLETE,
            payload=request.build_complete_payload(wavelength),
        )
        handled = controller.process_event(complete_event)
        if not handled:
            msg = "Mask selection completion was rejected during an active selection."
            raise InteractionStateError(msg)
        self.reset()
        return True
