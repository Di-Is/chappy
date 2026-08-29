"""Typed history commands for continuum control point operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.history.operation_id import OperationId

from .models import (
    HistoryApplyError,
    HistoryApplyResult,
    HistoryRefreshTarget,
    recoverable_history_apply_failure,
)

if TYPE_CHECKING:
    from .models import ChangeSet
    from .ports import ContinuumComponentSnapshot, ContinuumPointSnapshot, HistoryCommandContext


@dataclass(frozen=True, slots=True)
class ContinuumAddComponentCommand:
    """History command for adding one continuum component."""

    snapshot: ContinuumComponentSnapshot
    component_index: int

    def __post_init__(self) -> None:
        """Reject an invalid model insertion position."""
        if self.component_index < 0:
            msg = "Continuum component history index must be non-negative."
            raise ValueError(msg)

    @property
    def operation_id(self) -> OperationId:
        """Return the continuum component-add operation identifier."""
        return OperationId.CONT_ADD_COMPONENT

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Recreate the continuum component."""
        continuum_port = context.require_continuum_port()
        try:
            change_set = continuum_port.add_continuum_component(
                self.snapshot, index=self.component_index
            )
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _continuum_apply_success(change_set)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Remove the created continuum component."""
        continuum_port = context.require_continuum_port()
        try:
            change_set = continuum_port.remove_continuum_component(self.snapshot.component_id)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _continuum_apply_success(change_set)

    def is_noop(self) -> bool:
        """Return False because component creation always changes the model."""
        return False

    def coalesced_with(
        self, next_command: ContinuumAddComponentCommand
    ) -> ContinuumAddComponentCommand | None:
        """Continuum component creation commands are not coalesced."""
        _ = next_command
        return None


@dataclass(frozen=True, slots=True)
class ContinuumAddPointCommand:
    """History command for adding a continuum control point."""

    continuum_id: str
    before: tuple[ContinuumPointSnapshot, ...]
    after: tuple[ContinuumPointSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the continuum add operation identifier."""
        return OperationId.CONT_ADD_POINT

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore the complete point collection after addition."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore the complete point collection before addition."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether this command has no state change."""
        return self.before == self.after

    def coalesced_with(
        self, next_command: ContinuumAddPointCommand
    ) -> ContinuumAddPointCommand | None:
        """Continuum add commands are not coalesced."""
        _ = next_command
        return None

    def _apply(
        self, context: HistoryCommandContext, points: tuple[ContinuumPointSnapshot, ...]
    ) -> HistoryApplyResult:
        continuum_port = context.require_continuum_port()
        try:
            change_set = continuum_port.replace_continuum_points(self.continuum_id, points)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _continuum_apply_success(change_set)


@dataclass(frozen=True, slots=True)
class ContinuumDeletePointCommand:
    """History command for deleting a continuum control point."""

    continuum_id: str
    before: tuple[ContinuumPointSnapshot, ...]
    after: tuple[ContinuumPointSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the continuum delete operation identifier."""
        return OperationId.CONT_DELETE_POINT

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore the complete point collection after deletion."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore the complete point collection before deletion."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether this command has no state change."""
        return self.before == self.after

    def coalesced_with(
        self, next_command: ContinuumDeletePointCommand
    ) -> ContinuumDeletePointCommand | None:
        """Continuum delete commands are not coalesced."""
        _ = next_command
        return None

    def _apply(
        self, context: HistoryCommandContext, points: tuple[ContinuumPointSnapshot, ...]
    ) -> HistoryApplyResult:
        continuum_port = context.require_continuum_port()
        try:
            change_set = continuum_port.replace_continuum_points(self.continuum_id, points)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _continuum_apply_success(change_set)


@dataclass(frozen=True, slots=True)
class ContinuumMovePointCommand:
    """History command for moving a continuum control point."""

    continuum_id: str
    before: tuple[ContinuumPointSnapshot, ...]
    after: tuple[ContinuumPointSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the continuum move operation identifier."""
        return OperationId.CONT_MOVE_POINT

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Move the continuum point to its after position."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Move the continuum point back to its before position."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether before and after points are equal."""
        return self.before == self.after

    def coalesced_with(
        self, next_command: ContinuumMovePointCommand
    ) -> ContinuumMovePointCommand | None:
        """Continuum move commands are not coalesced."""
        _ = next_command
        return None

    def _apply(
        self, context: HistoryCommandContext, points: tuple[ContinuumPointSnapshot, ...]
    ) -> HistoryApplyResult:
        """Apply one continuum point movement through the configured port."""
        continuum_port = context.require_continuum_port()
        try:
            change_set = continuum_port.replace_continuum_points(self.continuum_id, points)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _continuum_apply_success(change_set)


@dataclass(frozen=True, slots=True)
class ContinuumResetCommand:
    """History command for replacing all continuum control points."""

    continuum_id: str
    before: tuple[ContinuumPointSnapshot, ...]
    after: tuple[ContinuumPointSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the continuum reset operation identifier."""
        return OperationId.CONT_RESET

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Replace control points with the after snapshot."""
        return self._apply(context, self.after)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Replace control points with the before snapshot."""
        return self._apply(context, self.before)

    def is_noop(self) -> bool:
        """Return whether before and after point snapshots are equal."""
        return self.before == self.after

    def coalesced_with(self, next_command: ContinuumResetCommand) -> ContinuumResetCommand | None:
        """Continuum reset commands are not coalesced."""
        _ = next_command
        return None

    def _apply(
        self, context: HistoryCommandContext, points: tuple[ContinuumPointSnapshot, ...]
    ) -> HistoryApplyResult:
        """Apply a full continuum point replacement through the configured port."""
        continuum_port = context.require_continuum_port()
        try:
            change_set = continuum_port.replace_continuum_points(self.continuum_id, points)
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _continuum_apply_success(change_set)


def _continuum_apply_success(change_set: ChangeSet) -> HistoryApplyResult:
    """Build the standard continuum command success result."""
    return HistoryApplyResult.ok(
        change_set=change_set, refresh_targets=(HistoryRefreshTarget.CONTINUUM_EDITOR,)
    )
