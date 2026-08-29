"""Mask selection controller coordinating mask creation and state snapshots."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from chappy.core.masking import MaskDefinition
from chappy.gui.protocols import MaskSelectionOverlayProtocol
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionId,
    InteractionOutcome,
    InteractionPhase,
    MaskSelectionContext,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.support.logging import InteractionLogEmitter

OverlayProvider = Callable[[], MaskSelectionOverlayProtocol | None]

# Minimum wavelength span for a mask (Angstroms)
MIN_MASK_WIDTH = 0.01


class MaskSelectionInteractionController:
    """Manage mask selection interactions and produce structured outcomes."""

    def __init__(
        self, *, log_emitter: InteractionLogEmitter, overlay_provider: OverlayProvider
    ) -> None:
        """Initialise the controller.

        Args:
            log_emitter: Structured logger used for phase transitions.
            overlay_provider: Callable returning the plot overlay implementation.
        """
        self._log_emitter = log_emitter
        self._overlay_provider = overlay_provider
        self._active = False
        self._selection_mode: str | None = None
        self._mask_id: str | None = None
        self._group_id: str | None = None
        self._start_pos: float | None = None
        self._initial_range: tuple[float, float] | None = None
        self._existing_mask: MaskDefinition | None = None
        self._interaction_id: InteractionId | None = None
        self._counter = 0

    def begin_selection(
        self,
        start_pos: float,
        *,
        selection_mode: str = "create",
        mask_id: str | None = None,
        group_id: str | None = None,
        initial_range: tuple[float, float] | None = None,
        existing_mask: MaskDefinition | None = None,
    ) -> InteractionOutcome[MaskSelectionContext]:
        """Record the selection starting point and emit an armed outcome.

        Args:
            start_pos: Starting wavelength position.
            selection_mode: Operation mode ("create" or "edit").
            mask_id: Identifier of the mask being edited (for edit mode).
            group_id: Identifier of the fitting group associated with the mask.
            initial_range: Initial wavelength range (for edit mode).
            existing_mask: Existing mask definition (for edit mode).

        Returns:
            Outcome with ARMED phase and initial context.
        """
        self._counter += 1
        interaction_id = InteractionId(f"mask-selection-{self._counter}")
        self._interaction_id = interaction_id
        self._selection_mode = selection_mode
        self._mask_id = mask_id
        self._group_id = group_id
        self._start_pos = start_pos
        self._initial_range = (
            (float(initial_range[0]), float(initial_range[1]))
            if initial_range is not None
            else None
        )
        self._existing_mask = existing_mask
        self._active = True
        overlay_range = self._initial_range
        self._begin_overlay(start_pos, overlay_range)

        payload = {
            "mode": selection_mode,
            "start": start_pos,
            "mask_id": mask_id,
            "group_id": group_id,
        }
        self._log_emitter.emit(InteractionPhase.ARMED, payload)

        context = MaskSelectionContext(
            selection_mode=selection_mode,
            mask_id=mask_id,
            group_id=group_id,
            start_pos=start_pos,
            current_pos=start_pos,
            end_pos=None,
            initial_range=initial_range,
            excluded_ranges=None,
            result_mask=None,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.MASK_SELECTION,
            phase=InteractionPhase.ARMED,
            context=context,
            interaction_id=interaction_id,
        )

    def update_selection(
        self, current_pos: float
    ) -> InteractionOutcome[MaskSelectionContext] | None:
        """Update the selection position and emit an active outcome.

        Args:
            current_pos: Current wavelength position.

        Returns:
            Outcome with ACTIVE phase, or None if not active.
        """
        if not self._active or self._start_pos is None or self._interaction_id is None:
            return None

        self._update_overlay(current_pos)

        payload = {"start": self._start_pos, "current": current_pos}
        self._log_emitter.emit(InteractionPhase.ACTIVE, payload)

        context = MaskSelectionContext(
            selection_mode=self._selection_mode,
            mask_id=self._mask_id,
            group_id=self._group_id,
            start_pos=self._start_pos,
            current_pos=current_pos,
            end_pos=None,
            initial_range=self._initial_range,
            excluded_ranges=None,
            result_mask=None,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.MASK_SELECTION,
            phase=InteractionPhase.ACTIVE,
            context=context,
            interaction_id=self._interaction_id,
        )

    def complete_selection(
        self, end_pos: float
    ) -> InteractionOutcome[MaskSelectionContext] | None:
        """Complete the selection, create/update mask definition, and emit an idle outcome.

        Args:
            end_pos: Final wavelength position.

        Returns:
            Outcome with IDLE phase and result mask, or None if not active.
        """
        if not self._active or self._start_pos is None or self._interaction_id is None:
            return None

        interaction_id = self._interaction_id

        # Normalize range (swap if needed)
        start_f = float(self._start_pos)
        end_f = float(end_pos)
        if end_f < start_f:
            start_f, end_f = end_f, start_f

        # Apply minimum width validation
        if end_f - start_f < MIN_MASK_WIDTH:
            end_f = start_f + MIN_MASK_WIDTH

        # Create or update mask definition
        result_mask: MaskDefinition
        if self._selection_mode == "edit" and self._existing_mask is not None:
            # Edit mode: update existing mask
            result_mask = self._existing_mask.with_range(start_f, end_f)
            # Preserve group_id from existing mask if present
            if self._existing_mask.group_id is not None:
                result_mask = result_mask.with_group_id(self._existing_mask.group_id)
            elif self._group_id is not None:
                result_mask = result_mask.with_group_id(self._group_id)
        else:
            # Create mode: create new mask
            result_mask = MaskDefinition.from_range(start_f, end_f)
            if self._group_id is not None:
                result_mask = result_mask.with_group_id(self._group_id)

        payload = {
            "mode": self._selection_mode,
            "start": start_f,
            "end": end_f,
            "mask_id": result_mask.identifier,
            "group_id": result_mask.group_id,
        }
        self._log_emitter.emit(InteractionPhase.IDLE, payload)

        context = MaskSelectionContext(
            selection_mode=self._selection_mode,
            mask_id=result_mask.identifier,
            group_id=result_mask.group_id,
            start_pos=start_f,
            current_pos=end_f,
            end_pos=end_f,
            initial_range=self._initial_range,
            excluded_ranges=None,
            result_mask=result_mask,
            cancel_reason=None,
        )
        self._reset_state()
        self._clear_overlay()

        return InteractionOutcome(
            channel=InteractionChannel.MASK_SELECTION,
            phase=InteractionPhase.IDLE,
            context=context,
            interaction_id=interaction_id,
        )

    def cancel_selection(
        self, reason: str | None = None
    ) -> InteractionOutcome[MaskSelectionContext] | None:
        """Cancel the selection and emit a cancelled outcome.

        Args:
            reason: Optional textual reason for cancellation.

        Returns:
            Outcome with CANCELLED phase, or None if not active.
        """
        if self._interaction_id is None:
            return None

        interaction_id = self._interaction_id
        self._reset_state()
        self._clear_overlay()

        payload = {"reason": reason} if reason else None
        self._log_emitter.emit(InteractionPhase.CANCELLED, payload)

        context = MaskSelectionContext(
            selection_mode=None,
            mask_id=None,
            group_id=None,
            start_pos=None,
            current_pos=None,
            end_pos=None,
            initial_range=None,
            excluded_ranges=None,
            result_mask=None,
            cancel_reason=reason,
        )
        return InteractionOutcome(
            channel=InteractionChannel.MASK_SELECTION,
            phase=InteractionPhase.CANCELLED,
            context=context,
            interaction_id=interaction_id,
        )

    def _reset_state(self) -> None:
        """Reset controller state to idle values."""
        self._active = False
        self._selection_mode = None
        self._mask_id = None
        self._group_id = None
        self._start_pos = None
        self._initial_range = None
        self._existing_mask = None
        self._interaction_id = None

    def _begin_overlay(self, start_pos: float, initial_range: tuple[float, float] | None) -> None:
        """Initialise overlay visuals for mask selection."""
        overlay = self._overlay_provider()
        if overlay is None:
            return
        overlay.begin_mask_selection(start_pos)
        current = start_pos
        if initial_range is not None:
            _start_hint, end_hint = initial_range
            current = float(end_hint)
        overlay.update_mask_selection(start_pos, current)

    def _update_overlay(self, current_pos: float) -> None:
        """Update overlay bounds based on current selection."""
        overlay = self._overlay_provider()
        if overlay is None or self._start_pos is None:
            return
        overlay.update_mask_selection(self._start_pos, current_pos)

    def _clear_overlay(self) -> None:
        """Clear the overlay if the provider supports it."""
        overlay = self._overlay_provider()
        if overlay is None:
            return
        overlay.clear_mask_selection()
