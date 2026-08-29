"""Typed history commands for identify operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.history.operation_id import OperationId

from .models import (
    ChangeSet,
    HistoryApplyError,
    HistoryApplyResult,
    HistoryRefreshTarget,
    recoverable_history_apply_failure,
)

if TYPE_CHECKING:
    from chappy.application.identify import CandidateLineSnapshot

    from .ports import AbsorptionLineSnapshot, AbsorptionRegionSnapshot, HistoryCommandContext


@dataclass(frozen=True, slots=True)
class IdentifyAddCandidateCommand:
    """History command for adding identify candidate lines."""

    snapshots: tuple[CandidateLineSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the identify candidate add operation identifier."""
        return OperationId.IDENT_ADD_CANDIDATE

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore added identify candidates."""
        return _restore_candidates(context, self.snapshots)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Remove added identify candidates."""
        return _remove_candidates(context, _candidate_ids(self.snapshots))

    def is_noop(self) -> bool:
        """Return whether the command has no candidate snapshots."""
        return not self.snapshots

    def coalesced_with(
        self, next_command: IdentifyAddCandidateCommand
    ) -> IdentifyAddCandidateCommand | None:
        """Identify candidate additions are not coalesced."""
        _ = next_command
        return None


@dataclass(frozen=True, slots=True)
class IdentifyRemoveCandidateCommand:
    """History command for removing identify candidate lines."""

    system_ids: tuple[str, ...]
    snapshots: tuple[CandidateLineSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the identify candidate remove operation identifier."""
        return OperationId.IDENT_REMOVE_CANDIDATE

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Remove identify candidates."""
        return _remove_candidates(context, self.system_ids)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore removed identify candidates."""
        return _restore_candidates(context, self.snapshots)

    def is_noop(self) -> bool:
        """Return whether the command has no candidate snapshots."""
        return not self.snapshots

    def coalesced_with(
        self, next_command: IdentifyRemoveCandidateCommand
    ) -> IdentifyRemoveCandidateCommand | None:
        """Identify candidate removals are not coalesced."""
        _ = next_command
        return None


@dataclass(frozen=True, slots=True)
class IdentifyClearCandidatesCommand:
    """History command for clearing identify candidate lines."""

    snapshots: tuple[CandidateLineSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the identify candidate clear operation identifier."""
        return OperationId.IDENT_CLEAR_CANDIDATES

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Clear identify candidates."""
        identify_port = context.require_identify_port()
        try:
            change_set = identify_port.clear_identify_candidates()
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _identify_result(change_set)

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Restore cleared identify candidates."""
        return _restore_candidates(context, self.snapshots)

    def is_noop(self) -> bool:
        """Return whether the command has no candidate snapshots."""
        return not self.snapshots

    def coalesced_with(
        self, next_command: IdentifyClearCandidatesCommand
    ) -> IdentifyClearCandidatesCommand | None:
        """Identify candidate clears are not coalesced."""
        _ = next_command
        return None


@dataclass(frozen=True, slots=True)
class IdentifyRegisterSelectedCommand:
    """History command for registering selected identify candidates."""

    created_line_ids: tuple[str, ...]
    removed_system_ids: tuple[str, ...]
    candidate_snapshots: tuple[CandidateLineSnapshot, ...]
    affected_region_ids: tuple[str, ...]
    line_snapshots: tuple[AbsorptionLineSnapshot, ...]
    before_affected_region_snapshots: tuple[AbsorptionRegionSnapshot, ...]
    after_affected_region_snapshots: tuple[AbsorptionRegionSnapshot, ...]

    @property
    def operation_id(self) -> OperationId:
        """Return the identify register operation identifier."""
        return OperationId.IDENT_REGISTER_SELECTED

    @property
    def qualifier(self) -> str | None:
        """Return no operation qualifier."""
        return None

    def redo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Reapply candidate registration."""
        identify_port = context.require_identify_port()
        organize_port = context.require_organize_port()
        try:
            candidate_changes = identify_port.remove_identify_candidates(self.removed_system_ids)
            before_ids = {snapshot.region_id for snapshot in self.before_affected_region_snapshots}
            created_regions = tuple(
                snapshot
                for snapshot in self.after_affected_region_snapshots
                if snapshot.region_id not in before_ids
            )
            region_changes = organize_port.restore_absorption_regions(created_regions)
            line_changes = organize_port.restore_absorption_lines(
                self.line_snapshots, restore_multiplet_links=True
            )
            analysis_changes = organize_port.apply_absorption_region_states_partial_exact(
                self.after_affected_region_snapshots
            )
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _registration_result(
            _merge_change_sets(candidate_changes, region_changes, line_changes, analysis_changes)
        )

    def undo(self, context: HistoryCommandContext) -> HistoryApplyResult:
        """Revert candidate registration."""
        identify_port = context.require_identify_port()
        organize_port = context.require_organize_port()
        try:
            line_changes = organize_port.remove_absorption_lines(
                self.created_line_ids, delete_models=False
            )
            candidate_changes = identify_port.restore_identify_candidates(self.candidate_snapshots)
            analysis_changes = organize_port.apply_absorption_region_states_partial_exact(
                self.before_affected_region_snapshots
            )
        except HistoryApplyError as error:
            return recoverable_history_apply_failure(error)
        return _registration_result(
            _merge_change_sets(line_changes, candidate_changes, analysis_changes)
        )

    def is_noop(self) -> bool:
        """Return whether the command has no created lines or candidates."""
        return not self.created_line_ids and not self.candidate_snapshots

    def coalesced_with(
        self, next_command: IdentifyRegisterSelectedCommand
    ) -> IdentifyRegisterSelectedCommand | None:
        """Identify registration commands are not coalesced."""
        _ = next_command
        return None


def _candidate_ids(snapshots: tuple[CandidateLineSnapshot, ...]) -> tuple[str, ...]:
    """Return candidate IDs from snapshots."""
    return tuple(snapshot.system_id for snapshot in snapshots)


def _restore_candidates(
    context: HistoryCommandContext, snapshots: tuple[CandidateLineSnapshot, ...]
) -> HistoryApplyResult:
    """Restore identify candidates through the identify port."""
    identify_port = context.require_identify_port()
    try:
        change_set = identify_port.restore_identify_candidates(snapshots)
    except HistoryApplyError as error:
        return recoverable_history_apply_failure(error)
    return _identify_result(change_set)


def _remove_candidates(
    context: HistoryCommandContext, system_ids: tuple[str, ...]
) -> HistoryApplyResult:
    """Remove identify candidates through the identify port."""
    identify_port = context.require_identify_port()
    try:
        change_set = identify_port.remove_identify_candidates(system_ids)
    except HistoryApplyError as error:
        return recoverable_history_apply_failure(error)
    return _identify_result(change_set)


def _identify_result(change_set: ChangeSet) -> HistoryApplyResult:
    """Return an identify-panel refresh result."""
    return HistoryApplyResult.ok(
        change_set=change_set, refresh_targets=(HistoryRefreshTarget.IDENTIFY_PANEL,)
    )


def _registration_result(change_set: ChangeSet) -> HistoryApplyResult:
    """Return an identify registration refresh result."""
    return HistoryApplyResult.ok(
        change_set=change_set,
        refresh_targets=(HistoryRefreshTarget.IDENTIFY_PANEL, HistoryRefreshTarget.ORGANIZE_PANEL),
    )


def _merge_change_sets(*change_sets: ChangeSet) -> ChangeSet:
    """Merge change sets while preserving first-seen order."""
    component_ids: list[str] = []
    line_ids: list[str] = []
    region_ids: list[str] = []
    candidate_ids: list[str] = []
    continuum_ids: list[str] = []
    for change_set in change_sets:
        _extend_unique(component_ids, change_set.changed_component_ids)
        _extend_unique(line_ids, change_set.changed_line_ids)
        _extend_unique(region_ids, change_set.changed_region_ids)
        _extend_unique(candidate_ids, change_set.changed_candidate_ids)
        _extend_unique(continuum_ids, change_set.changed_continuum_ids)
    return ChangeSet(
        changed_component_ids=tuple(component_ids),
        changed_line_ids=tuple(line_ids),
        changed_region_ids=tuple(region_ids),
        changed_candidate_ids=tuple(candidate_ids),
        changed_continuum_ids=tuple(continuum_ids),
    )


def _extend_unique(target: list[str], values: tuple[str, ...]) -> None:
    """Append values not already present in the target list."""
    for value in values:
        if value not in target:
            target.append(value)
