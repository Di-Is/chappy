"""Tests for continuum editing controller."""

from __future__ import annotations

import pytest

from chappy.gui.modes.continuum.controllers.interaction_controller import (
    ContinuumInteractionController,
)
from chappy.presentation.interaction.interaction_contracts import (
    ContinuumOperationType,
    InteractionChannel,
    InteractionPhase,
)
from chappy.gui.spectrum.interaction.support.logging import InteractionLogEmitter
from chappy.presentation.spectrum.visual_tokens import ContinuumControlPointVisuals


class TestContinuumInteractionController:
    """Test suite for ContinuumInteractionController."""

    @pytest.fixture
    def log_emitter(self):
        """Return a log emitter for continuum channel."""
        return InteractionLogEmitter(channel=InteractionChannel.CONTINUUM)

    @pytest.fixture
    def current_points(self):
        """Return a callable that returns current points."""
        return lambda: [(4000.0, 1.0), (4500.0, 1.0), (5000.0, 1.0), (5500.0, 1.0)]

    @pytest.fixture
    def controller(self, log_emitter, current_points):
        """Return a ContinuumInteractionController instance."""
        return ContinuumInteractionController(
            log_emitter=log_emitter, current_points=current_points
        )

    def test_controller_initialization(self, controller):
        """Test that controller initializes correctly."""
        assert controller is not None

    def test_begin_add_valid(self, controller):
        """Test beginning an add operation with valid coordinates."""
        outcome = controller.begin_add((4200.0, 1.0))

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.ARMED
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.ADD
        assert outcome.context.point_index is None
        assert outcome.context.start_position == (4200.0, 1.0)
        assert outcome.context.current_position == (4200.0, 1.0)
        assert outcome.context.validation_result is None

    def test_begin_add_too_close(self, controller):
        """Test beginning an add operation with coordinates too close to existing point."""
        # Try to add a point very close to the first existing point (4000.0)
        outcome = controller.begin_add((4000.05, 1.0))

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.CANCELLED
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.ADD
        assert outcome.context.validation_result is not None
        assert outcome.context.validation_result.reason == "too_close"

    def test_begin_add_limit_reached(self, log_emitter):
        """Test beginning an add operation when limit is reached."""
        # Create a controller with max points
        max_points = [(4000.0 + i * 10.0, 1.0) for i in range(ContinuumControlPointVisuals.LIMIT)]
        controller = ContinuumInteractionController(
            log_emitter=log_emitter, current_points=lambda: max_points
        )

        outcome = controller.begin_add((10000.0, 1.0))

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.CANCELLED
        assert outcome.context is not None
        assert outcome.context.validation_result is not None
        assert outcome.context.validation_result.reason == "limit_reached"

    def test_begin_add_flux_none(self, controller):
        """Test beginning an add operation with None flux."""
        outcome = controller.begin_add((4200.0, None))

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.CANCELLED
        assert outcome.context is not None
        assert outcome.context.validation_result is not None
        assert outcome.context.validation_result.reason == "flux_required"

    def test_begin_move(self, controller):
        """Test beginning a move operation."""
        outcome = controller.begin_move(0, (4000.0, 1.0))

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.ARMED
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.MOVE
        assert outcome.context.point_index == 0
        assert outcome.context.start_position == (4000.0, 1.0)

    def test_update_move_valid(self, controller):
        """Test updating a move operation with valid coordinates."""
        controller.begin_move(0, (4000.0, 1.0))
        outcome = controller.update((4100.0, 1.1))

        assert outcome is not None
        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.ACTIVE
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.MOVE
        assert outcome.context.current_position == (4100.0, 1.1)
        assert outcome.context.validation_result is None

    def test_update_move_too_close(self, controller):
        """Test updating a move operation with coordinates too close to another point."""
        controller.begin_move(0, (4000.0, 1.0))
        # Try to move point 0 too close to point 1 (4500.0)
        outcome = controller.update((4500.05, 1.0))

        assert outcome is not None
        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.ACTIVE
        assert outcome.context is not None
        assert outcome.context.validation_result is not None
        assert outcome.context.validation_result.reason == "too_close"

    def test_complete_move(self, controller):
        """Test completing a move operation."""
        controller.begin_move(0, (4000.0, 1.0))
        controller.update((4100.0, 1.1))
        outcome = controller.complete((4100.0, 1.1))

        assert outcome is not None
        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.IDLE
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.MOVE
        assert outcome.context.end_position == (4100.0, 1.1)

    def test_begin_delete_valid(self, controller):
        """Test beginning a delete operation with valid conditions."""
        outcome = controller.begin_delete(0)

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.ARMED
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.DELETE
        assert outcome.context.point_index == 0
        assert outcome.context.validation_result is None

    def test_begin_delete_minimum_points(self, log_emitter):
        """Test beginning a delete operation when only minimum points exist."""
        # Create a controller with exactly 3 points (minimum)
        controller = ContinuumInteractionController(
            log_emitter=log_emitter,
            current_points=lambda: [(4000.0, 1.0), (4500.0, 1.0), (5000.0, 1.0)],
        )

        outcome = controller.begin_delete(0)

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.CANCELLED
        assert outcome.context is not None
        assert outcome.context.validation_result is not None
        assert outcome.context.validation_result.reason == "minimum_points"

    def test_complete_delete(self, controller):
        """Test completing a delete operation."""
        controller.begin_delete(0)
        outcome = controller.complete(None)

        assert outcome is not None
        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.IDLE
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.DELETE

    def test_begin_select(self, controller):
        """Test beginning a select operation."""
        outcome = controller.begin_select(1)

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.IDLE
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.SELECT
        assert outcome.context.point_index == 1

    def test_begin_select_none(self, controller):
        """Test beginning a select operation with None (clear selection)."""
        outcome = controller.begin_select(None)

        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.IDLE
        assert outcome.context is not None
        assert outcome.context.operation_type == ContinuumOperationType.SELECT
        assert outcome.context.point_index is None

    def test_cancel_operation(self, controller):
        """Test cancelling an operation."""
        controller.begin_move(0, (4000.0, 1.0))
        outcome = controller.cancel(reason="user-cancelled")

        assert outcome is not None
        assert outcome.channel == InteractionChannel.CONTINUUM
        assert outcome.phase == InteractionPhase.CANCELLED
        assert outcome.context is not None
        assert outcome.context.cancel_reason == "user-cancelled"

    def test_update_without_active_operation(self, controller):
        """Test that update returns None when no operation is active."""
        outcome = controller.update((4100.0, 1.1))

        assert outcome is None

    def test_complete_without_active_operation(self, controller):
        """Test that complete returns None when no operation is active."""
        outcome = controller.complete((4100.0, 1.1))

        assert outcome is None

    def test_cancel_without_active_operation(self, controller):
        """Test that cancel returns None when no operation is active."""
        outcome = controller.cancel(reason="test")

        assert outcome is None
