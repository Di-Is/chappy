"""Smoke tests for MaskSelectionInteractionController."""

from __future__ import annotations

from chappy.core.masking import MaskDefinition
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionPhase,
    MaskSelectionContext,
)
from chappy.gui.spectrum.interaction.support.logging import InteractionLogEmitter
from chappy.gui.spectrum.interaction.channels.mask_selection.interaction_controller import (
    MIN_MASK_WIDTH,
    MaskSelectionInteractionController,
)


def _build_controller() -> MaskSelectionInteractionController:
    """Build a mask selection controller for testing."""
    emitter = InteractionLogEmitter(channel=InteractionChannel.MASK_SELECTION)
    controller = MaskSelectionInteractionController(
        log_emitter=emitter, overlay_provider=lambda: None
    )
    return controller


def test_controller_initialization() -> None:
    """Verify controller initializes without errors."""
    controller = _build_controller()
    assert controller is not None


def test_create_mode_lifecycle() -> None:
    """Verify create mode produces correct outcomes and context."""
    controller = _build_controller()

    # Begin selection
    outcome_begin = controller.begin_selection(
        5000.0, selection_mode="create", group_id="test-group"
    )
    assert outcome_begin.channel == InteractionChannel.MASK_SELECTION
    assert outcome_begin.phase == InteractionPhase.ARMED
    assert isinstance(outcome_begin.context, MaskSelectionContext)
    assert outcome_begin.context.selection_mode == "create"
    assert outcome_begin.context.group_id == "test-group"
    assert outcome_begin.context.start_pos == 5000.0
    assert outcome_begin.context.result_mask is None

    # Update selection
    outcome_update = controller.update_selection(5010.0)
    assert outcome_update is not None
    assert outcome_update.phase == InteractionPhase.ACTIVE
    assert outcome_update.context.current_pos == 5010.0

    # Complete selection
    outcome_complete = controller.complete_selection(5020.0)
    assert outcome_complete is not None
    assert outcome_complete.phase == InteractionPhase.IDLE
    assert outcome_complete.context.end_pos == 5020.0
    assert outcome_complete.context.result_mask is not None
    result_mask = outcome_complete.context.result_mask
    assert result_mask.start_wavelength == 5000.0
    assert result_mask.end_wavelength == 5020.0
    assert result_mask.group_id == "test-group"


def test_edit_mode_with_existing_mask() -> None:
    """Verify edit mode updates existing mask correctly."""
    controller = _build_controller()

    # Create an existing mask
    existing_mask = MaskDefinition.from_range(5000.0, 5010.0).with_group_id("existing-group")

    # Begin edit selection
    outcome_begin = controller.begin_selection(
        5005.0,
        selection_mode="edit",
        mask_id=existing_mask.identifier,
        group_id="existing-group",
        initial_range=(5000.0, 5010.0),
        existing_mask=existing_mask,
    )
    assert outcome_begin.phase == InteractionPhase.ARMED
    assert outcome_begin.context.selection_mode == "edit"
    assert outcome_begin.context.mask_id == existing_mask.identifier

    # Complete edit with new range
    outcome_complete = controller.complete_selection(5025.0)
    assert outcome_complete is not None
    assert outcome_complete.phase == InteractionPhase.IDLE
    result_mask = outcome_complete.context.result_mask
    assert result_mask is not None
    assert result_mask.start_wavelength == 5005.0
    assert result_mask.end_wavelength == 5025.0
    assert result_mask.group_id == "existing-group"  # Preserved from existing mask


def test_cancel_returns_cancelled_outcome() -> None:
    """Verify cancel produces CANCELLED outcome."""
    controller = _build_controller()

    # Begin selection
    controller.begin_selection(5000.0, selection_mode="create")

    # Cancel
    outcome_cancel = controller.cancel_selection(reason="user-cancelled")
    assert outcome_cancel is not None
    assert outcome_cancel.phase == InteractionPhase.CANCELLED
    assert outcome_cancel.context.cancel_reason == "user-cancelled"
    assert outcome_cancel.context.result_mask is None


def test_minimum_width_validation() -> None:
    """Verify minimum width validation is applied."""
    controller = _build_controller()

    # Begin with very small range
    controller.begin_selection(5000.0, selection_mode="create")
    outcome_complete = controller.complete_selection(5000.005)  # Less than MIN_MASK_WIDTH

    assert outcome_complete is not None
    result_mask = outcome_complete.context.result_mask
    assert result_mask is not None
    # Should be expanded to MIN_MASK_WIDTH
    assert result_mask.end_wavelength == 5000.0 + MIN_MASK_WIDTH


def test_range_normalization() -> None:
    """Verify range is normalized (swapped if start > end)."""
    controller = _build_controller()

    # Begin with larger start
    controller.begin_selection(5020.0, selection_mode="create")
    outcome_complete = controller.complete_selection(5010.0)  # end < start

    assert outcome_complete is not None
    result_mask = outcome_complete.context.result_mask
    assert result_mask is not None
    # Should be swapped
    assert result_mask.start_wavelength == 5010.0
    assert result_mask.end_wavelength == 5020.0


def test_update_without_begin_returns_none() -> None:
    """Verify update without begin returns None."""
    controller = _build_controller()

    outcome_update = controller.update_selection(5010.0)
    assert outcome_update is None


def test_complete_without_begin_returns_none() -> None:
    """Verify complete without begin returns None."""
    controller = _build_controller()

    outcome_complete = controller.complete_selection(5020.0)
    assert outcome_complete is None
