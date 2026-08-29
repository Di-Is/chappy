"""Continuum editing controller coordinating validation and state snapshots."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chappy.presentation.interaction.interaction_contracts import (
    ContinuumContext,
    ContinuumOperationType,
    Coordinate,
    InteractionChannel,
    InteractionId,
    InteractionOutcome,
    InteractionPhase,
    ValidationError,
)
from chappy.presentation.spectrum.visual_tokens import ContinuumControlPointVisuals

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.spectrum.interaction.support.logging import InteractionLogEmitter

logger = logging.getLogger(__name__)


class ContinuumInteractionController:
    """Manage continuum editing interactions and produce structured outcomes."""

    def __init__(
        self, *, log_emitter: InteractionLogEmitter, current_points: Callable[[], list[Coordinate]]
    ) -> None:
        """Initialise the controller.

        Args:
            log_emitter: Structured logger used for phase transitions.
            current_points: Callable returning the current list of continuum points.
        """
        self._log_emitter = log_emitter
        self._current_points = current_points
        self._active_operation: str | None = None
        self._point_index: int | None = None
        self._start: Coordinate | None = None
        self._current: Coordinate | None = None
        self._interaction_id: InteractionId | None = None
        self._counter = 0

    def begin_add(self, position: Coordinate) -> InteractionOutcome[ContinuumContext]:
        """Begin adding a new continuum point.

        Args:
            position: Wavelength and flux coordinate for the new point.

        Returns:
            Outcome with ARMED phase if validation passes, or CANCELLED if it fails.
        """
        self._counter += 1
        interaction_id = InteractionId(f"continuum-add-{self._counter}")
        self._interaction_id = interaction_id
        self._active_operation = ContinuumOperationType.ADD.value
        self._point_index = None
        self._start = position
        self._current = position

        wavelength, flux = position
        validation_result = self._validate_add(wavelength, flux)

        if validation_result is not None:
            # Validation failed
            payload = {"position": list(position), "validation": validation_result.reason}
            self._log_emitter.emit(InteractionPhase.CANCELLED, payload)
            context = ContinuumContext(
                operation_type=ContinuumOperationType.ADD,
                point_index=None,
                start_position=position,
                current_position=position,
                end_position=None,
                validation_result=validation_result,
                cancel_reason=validation_result.reason,
            )
            self._reset_state()
            return InteractionOutcome(
                channel=InteractionChannel.CONTINUUM,
                phase=InteractionPhase.CANCELLED,
                context=context,
                interaction_id=interaction_id,
            )

        # Validation passed
        payload = {"position": list(position)}
        self._log_emitter.emit(InteractionPhase.ARMED, payload)

        context = ContinuumContext(
            operation_type=ContinuumOperationType.ADD,
            point_index=None,
            start_position=position,
            current_position=position,
            end_position=None,
            validation_result=None,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ARMED,
            context=context,
            interaction_id=interaction_id,
        )

    def begin_move(
        self, point_index: int, start: Coordinate
    ) -> InteractionOutcome[ContinuumContext]:
        """Begin moving an existing continuum point.

        Args:
            point_index: Index of the point to move.
            start: Starting coordinate of the drag.

        Returns:
            Outcome with ARMED phase.
        """
        self._counter += 1
        interaction_id = InteractionId(f"continuum-move-{self._counter}")
        self._interaction_id = interaction_id
        self._active_operation = ContinuumOperationType.MOVE.value
        self._point_index = point_index
        self._start = start
        self._current = start

        payload = {"point_index": point_index, "start": list(start)}
        self._log_emitter.emit(InteractionPhase.ARMED, payload)

        context = ContinuumContext(
            operation_type=ContinuumOperationType.MOVE,
            point_index=point_index,
            start_position=start,
            current_position=start,
            end_position=None,
            validation_result=None,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ARMED,
            context=context,
            interaction_id=interaction_id,
        )

    def begin_delete(self, point_index: int) -> InteractionOutcome[ContinuumContext]:
        """Begin deleting a continuum point.

        Args:
            point_index: Index of the point to delete.

        Returns:
            Outcome with ARMED phase if validation passes, or CANCELLED if it fails.
        """
        self._counter += 1
        interaction_id = InteractionId(f"continuum-delete-{self._counter}")
        self._interaction_id = interaction_id
        self._active_operation = ContinuumOperationType.DELETE.value
        self._point_index = point_index
        self._start = None
        self._current = None

        validation_result = self._validate_delete()

        if validation_result is not None:
            # Validation failed
            payload = {"point_index": point_index, "validation": validation_result.reason}
            self._log_emitter.emit(InteractionPhase.CANCELLED, payload)
            context = ContinuumContext(
                operation_type=ContinuumOperationType.DELETE,
                point_index=point_index,
                start_position=None,
                current_position=None,
                end_position=None,
                validation_result=validation_result,
                cancel_reason=validation_result.reason,
            )
            self._reset_state()
            return InteractionOutcome(
                channel=InteractionChannel.CONTINUUM,
                phase=InteractionPhase.CANCELLED,
                context=context,
                interaction_id=interaction_id,
            )

        # Validation passed
        payload = {"point_index": point_index}
        self._log_emitter.emit(InteractionPhase.ARMED, payload)

        context = ContinuumContext(
            operation_type=ContinuumOperationType.DELETE,
            point_index=point_index,
            start_position=None,
            current_position=None,
            end_position=None,
            validation_result=None,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ARMED,
            context=context,
            interaction_id=interaction_id,
        )

    def begin_select(self, point_index: int | None) -> InteractionOutcome[ContinuumContext]:
        """Begin selecting a continuum point.

        Args:
            point_index: Index of the point to select, or None to clear selection.

        Returns:
            Outcome with IDLE phase (selection is immediate).
        """
        self._counter += 1
        interaction_id = InteractionId(f"continuum-select-{self._counter}")
        self._interaction_id = interaction_id
        self._active_operation = ContinuumOperationType.SELECT.value
        self._point_index = point_index
        self._start = None
        self._current = None

        payload = {"point_index": point_index}
        self._log_emitter.emit(InteractionPhase.IDLE, payload)

        context = ContinuumContext(
            operation_type=ContinuumOperationType.SELECT,
            point_index=point_index,
            start_position=None,
            current_position=None,
            end_position=None,
            validation_result=None,
            cancel_reason=None,
        )
        self._reset_state()

        return InteractionOutcome(
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.IDLE,
            context=context,
            interaction_id=interaction_id,
        )

    def update(self, current: Coordinate) -> InteractionOutcome[ContinuumContext] | None:
        """Update the current position during a move operation.

        Args:
            current: Current coordinate during drag.

        Returns:
            Outcome with ACTIVE phase if move is active, None otherwise.
        """
        if (
            self._active_operation != ContinuumOperationType.MOVE.value
            or self._point_index is None
            or self._interaction_id is None
        ):
            return None

        self._current = current
        wavelength, _flux = current

        validation_result = self._validate_move(self._point_index, wavelength)

        payload = {
            "point_index": self._point_index,
            "current": list(current),
            "valid": validation_result is None,
        }
        self._log_emitter.emit(InteractionPhase.ACTIVE, payload)

        context = ContinuumContext(
            operation_type=ContinuumOperationType.MOVE,
            point_index=self._point_index,
            start_position=self._start,
            current_position=current,
            end_position=None,
            validation_result=validation_result,
            cancel_reason=None,
        )
        return InteractionOutcome(
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ACTIVE,
            context=context,
            interaction_id=self._interaction_id,
        )

    def complete(
        self, end: Coordinate | None = None
    ) -> InteractionOutcome[ContinuumContext] | None:
        """Complete the current operation.

        Args:
            end: Final coordinate (for move/add operations), None for delete/select.

        Returns:
            Outcome with IDLE phase if operation is active, None otherwise.
        """
        if self._interaction_id is None:
            return None

        interaction_id = self._interaction_id
        operation = self._active_operation

        if (
            operation == ContinuumOperationType.MOVE.value
            and self._point_index is not None
            and end is not None
        ):
            # Validate final position
            wavelength, _flux = end
            validation_result = self._validate_move(self._point_index, wavelength)

            payload = {
                "point_index": self._point_index,
                "end": list(end),
                "valid": validation_result is None,
            }
            self._log_emitter.emit(InteractionPhase.IDLE, payload)

            context = ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=self._point_index,
                start_position=self._start,
                current_position=end,
                end_position=end,
                validation_result=validation_result,
                cancel_reason=None,
            )
        elif operation == ContinuumOperationType.ADD.value and end is not None:
            payload = {"position": list(end)}
            self._log_emitter.emit(InteractionPhase.IDLE, payload)

            context = ContinuumContext(
                operation_type=ContinuumOperationType.ADD,
                point_index=None,
                start_position=self._start,
                current_position=end,
                end_position=end,
                validation_result=None,
                cancel_reason=None,
            )
        elif operation == ContinuumOperationType.DELETE.value and self._point_index is not None:
            payload = {"point_index": self._point_index}
            self._log_emitter.emit(InteractionPhase.IDLE, payload)

            context = ContinuumContext(
                operation_type=ContinuumOperationType.DELETE,
                point_index=self._point_index,
                start_position=None,
                current_position=None,
                end_position=None,
                validation_result=None,
                cancel_reason=None,
            )
        else:
            # Invalid state
            self._reset_state()
            return None

        self._reset_state()

        return InteractionOutcome(
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.IDLE,
            context=context,
            interaction_id=interaction_id,
        )

    def cancel(self, reason: str | None = None) -> InteractionOutcome[ContinuumContext] | None:
        """Cancel the current operation.

        Args:
            reason: Optional reason for cancellation.

        Returns:
            Outcome with CANCELLED phase if operation is active, None otherwise.
        """
        if self._interaction_id is None:
            return None

        interaction_id = self._interaction_id
        operation = self._active_operation
        point_index = self._point_index

        payload = (
            {"reason": reason, "operation": operation} if reason else {"operation": operation}
        )
        self._log_emitter.emit(InteractionPhase.CANCELLED, payload)

        # Convert operation string to enum
        operation_type: ContinuumOperationType | None = None
        if operation is not None:
            try:
                operation_type = ContinuumOperationType(operation)
            except ValueError:
                logger.warning("Unknown operation type: %s", operation)
                operation_type = None

        context = ContinuumContext(
            operation_type=operation_type,
            point_index=point_index,
            start_position=self._start,
            current_position=self._current,
            end_position=None,
            validation_result=None,
            cancel_reason=reason,
        )
        self._reset_state()

        return InteractionOutcome(
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.CANCELLED,
            context=context,
            interaction_id=interaction_id,
        )

    def _validate_add(self, wavelength: float, flux: float | None) -> ValidationError | None:
        """Validate adding a new point.

        Args:
            wavelength: Wavelength of the new point.
            flux: Flux value of the new point.

        Returns:
            Validation error if validation fails, None if it passes.
        """
        if flux is None:
            return ValidationError(reason="flux_required", message="Flux value is required")

        points = self._current_points()
        if len(points) >= ContinuumControlPointVisuals.LIMIT:
            return ValidationError(
                reason="limit_reached",
                message=f"Maximum {ContinuumControlPointVisuals.LIMIT} points allowed",
            )

        if self._is_too_close_to_existing(wavelength):
            return self._build_too_close_error()

        return None

    def _validate_move(self, point_index: int, wavelength: float) -> ValidationError | None:
        """Validate moving a point.

        Args:
            point_index: Index of the point being moved.
            wavelength: New wavelength position.

        Returns:
            Validation error if validation fails, None if it passes.
        """
        if self._is_too_close_to_existing(wavelength, exclude_index=point_index):
            return self._build_too_close_error()

        return None

    def _validate_delete(self) -> ValidationError | None:
        """Validate deleting a point.

        Returns:
            Validation error if validation fails, None if it passes.
        """
        points = self._current_points()
        if len(points) <= ContinuumControlPointVisuals.MIN_POINTS_REQUIRED:
            return ValidationError(
                reason="minimum_points",
                message=f"At least {ContinuumControlPointVisuals.MIN_POINTS_REQUIRED} points are required",
            )

        return None

    def _build_too_close_error(self) -> ValidationError:
        """Build a validation error for points that are too close to existing points.

        Returns:
            ValidationError with too_close reason and formatted message.
        """
        return ValidationError(
            reason="too_close",
            message=f"Point too close to existing (min separation: {ContinuumControlPointVisuals.MIN_SEPARATION_ANGSTROM})",
        )

    def _is_too_close_to_existing(
        self, wavelength: float, exclude_index: int | None = None
    ) -> bool:
        """Check if a wavelength is too close to existing points.

        Args:
            wavelength: Wavelength to check.
            exclude_index: Optional index to exclude from the check.

        Returns:
            True if too close, False otherwise.
        """
        points = self._current_points()
        min_separation = ContinuumControlPointVisuals.MIN_SEPARATION_ANGSTROM

        for idx, (existing_wave, _flux) in enumerate(points):
            if exclude_index is not None and idx == exclude_index:
                continue
            if abs(existing_wave - wavelength) < min_separation:
                return True

        return False

    def _reset_state(self) -> None:
        """Reset controller state to idle values."""
        self._active_operation = None
        self._point_index = None
        self._start = None
        self._current = None
        self._interaction_id = None
