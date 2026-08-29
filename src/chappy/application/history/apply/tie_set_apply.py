"""Tie-set history application: topology and bound-parameter transitions."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import AnalysisMutationOutcome
from chappy.application.history import (
    ComponentParameterState,
    HistoryApplyError,
    HistoryApplyErrorCode,
    HistoryRefreshTarget,
    ScientificHistoryApplyExecution,
    ScientificHistoryScope,
    TieSetSnapshot,
)
from chappy.application.history.snapshot_builders import component_parameter_state
from chappy.application.history.snapshot_mapping import tie_set_snapshot
from chappy.core.change_set import ChangeSet as DomainChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.events import ComponentChanged

if TYPE_CHECKING:
    from chappy.application.history import (
        HistoryApplyResult,
        HistoryCommandContext,
        TieSetEditCommand,
    )
    from chappy.application.history.scientific_apply_executor import ScientificHistoryApplyExecutor
    from chappy.application.optimize.model_topology_usecase import AbsorberModelTopologyUseCase
    from chappy.core.spectroscopy_project import SpectroscopyProject


def validate_tie_snapshots(
    project: SpectroscopyProject,
    snapshots: tuple[TieSetSnapshot, ...],
    *,
    additional_component_ids: frozenset[str] = frozenset(),
) -> None:
    """Validate tie identities, references, nesting, and parameter targets."""
    by_uid: dict[str, TieSetSnapshot] = {}
    known_component_ids = {
        component.id
        for component in project.model.components
        if isinstance(component, AbsorberComponent)
    } | set(additional_component_ids)
    existing_uids = {tie_set.uid for tie_set in project.model.iter_tie_sets()}
    for snapshot in snapshots:
        if snapshot.uid in by_uid:
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Tie history has duplicate snapshots for uid: {snapshot.uid}",
            )
        by_uid[snapshot.uid] = snapshot
        if (
            not snapshot.uid
            or not snapshot.tie_id
            or snapshot.origin not in {"multiplet", "user"}
            or len(set(snapshot.component_ids)) != len(snapshot.component_ids)
            or len(set(snapshot.member_uids)) != len(snapshot.member_uids)
            or snapshot.uid in snapshot.member_uids
            or any(
                component_id not in known_component_ids for component_id in snapshot.component_ids
            )
        ):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Tie history snapshot topology is invalid: {snapshot.uid}",
            )
        if any(
            member_uid not in existing_uids
            and member_uid not in by_uid
            and member_uid not in {candidate.uid for candidate in snapshots}
            for member_uid in snapshot.member_uids
        ):
            raise HistoryApplyError(
                HistoryApplyErrorCode.TARGET_NOT_FOUND,
                f"Tie history nested member was not found: {snapshot.uid}",
            )
        names = tuple(parameter.name for parameter in snapshot.shared_parameters)
        if len(set(names)) != len(names) or set(names) != set(snapshot.mask):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Tie history shared parameters do not match the mask: {snapshot.uid}",
            )
        for parameter in snapshot.shared_parameters:
            if (
                parameter.min_value is None
                or parameter.max_value is None
                or parameter.error is None
                or parameter.min_value > parameter.max_value
                or not parameter.min_value <= parameter.value <= parameter.max_value
                or not math.isfinite(parameter.value)
            ):
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    f"Tie history parameter target is invalid: {snapshot.uid}.{parameter.name}",
                )


def validate_tie_snapshot_indices(
    snapshots: tuple[TieSetSnapshot, ...],
    indices: tuple[int, ...],
    *,
    total_count: int,
    label: str,
) -> None:
    """Validate an exact temporal tie-set placement before mutation."""
    if len(snapshots) != len(indices) or len(set(indices)) != len(indices):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            f"Tie history {label} snapshots and indices are inconsistent.",
        )
    if total_count < 0 or any(index < 0 or index >= total_count for index in indices):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE, f"Tie history {label} index is out of bounds."
        )


def validate_component_state_snapshots(
    project: SpectroscopyProject, states: tuple[ComponentParameterState, ...]
) -> None:
    """Validate complete component parameter snapshots without assuming bindings."""
    component_ids = tuple(state.component_id for state in states)
    if len(set(component_ids)) != len(component_ids):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Tie history component state identities must be unique.",
        )
    for state in states:
        component = project.find_absorber_component(state.component_id)
        if component is None:
            raise HistoryApplyError(
                HistoryApplyErrorCode.TARGET_NOT_FOUND,
                f"Tie history component not found: {state.component_id}",
            )
        names = tuple(parameter.name for parameter in state.parameters)
        if len(set(names)) != len(names) or set(names) != set(component.parameters):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Tie history component parameters do not match: {state.component_id}",
            )
        for parameter in state.parameters:
            current = component.parameters[parameter.name]
            minimum = current.min_val if parameter.min_value is None else parameter.min_value
            maximum = current.max_val if parameter.max_value is None else parameter.max_value
            if (
                minimum > maximum
                or not minimum <= parameter.value <= maximum
                or not math.isfinite(parameter.value)
            ):
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    f"Tie history component parameter is invalid: "
                    f"{state.component_id}.{parameter.name}",
                )


def tie_temporal_state_matches(
    project: SpectroscopyProject,
    uids: tuple[str, ...],
    snapshots: tuple[TieSetSnapshot, ...],
    indices: tuple[int, ...],
    states: tuple[ComponentParameterState, ...],
) -> bool:
    """Return whether selected tie topology and independent states match exactly."""
    uid_set = set(uids)
    current_ties = tuple(
        (tie_set.uid, tie_set_snapshot(tie_set), index)
        for index, tie_set in enumerate(project.model.iter_tie_sets())
        if tie_set.uid in uid_set
    )
    current_ties_by_uid = {uid: (snapshot, index) for uid, snapshot, index in current_ties}
    expected_ties = {
        snapshot.uid: (snapshot, index) for snapshot, index in zip(snapshots, indices, strict=True)
    }
    if len(current_ties) != len(current_ties_by_uid) or current_ties_by_uid != expected_ties:
        return False
    return all(
        (component := project.find_absorber_component(state.component_id)) is not None
        and component_parameter_state(component) == state
        for state in states
    )


def tie_history_component_ids(command: TieSetEditCommand) -> tuple[str, ...]:
    """Return every component touched by either tie history temporal state."""
    return tuple(
        dict.fromkeys(
            (
                *(
                    component_id
                    for snapshot in (*command.before_tie_sets, *command.after_tie_sets)
                    for component_id in snapshot.component_ids
                ),
                *(
                    state.component_id
                    for state in (
                        *command.before_component_states,
                        *command.after_component_states,
                    )
                ),
            )
        )
    )


def preflight_tie_set_history(
    project: SpectroscopyProject,
    command: TieSetEditCommand,
    *,
    target_tie_sets: tuple[TieSetSnapshot, ...],
    target_tie_set_indices: tuple[int, ...],
    source_tie_sets: tuple[TieSetSnapshot, ...],
    source_tie_set_indices: tuple[int, ...],
    target_states: tuple[ComponentParameterState, ...],
    source_states: tuple[ComponentParameterState, ...],
) -> AnalysisMutationOutcome:
    """Validate both temporal tie topologies before changing any binding."""
    if not command.uids or len(set(command.uids)) != len(command.uids):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE, "Tie history uids must be non-empty and unique."
        )
    snapshot_uids = {
        snapshot.uid for snapshot in (*command.before_tie_sets, *command.after_tie_sets)
    }
    if not snapshot_uids.issubset(set(command.uids)):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE, "Tie history snapshots contain undeclared uids."
        )
    validate_tie_snapshots(project, command.before_tie_sets)
    validate_tie_snapshots(project, command.after_tie_sets)
    validate_component_state_snapshots(project, command.before_component_states)
    validate_component_state_snapshots(project, command.after_component_states)

    current_tie_count = len(tuple(project.model.iter_tie_sets()))
    target_matches = tie_temporal_state_matches(
        project, command.uids, target_tie_sets, target_tie_set_indices, target_states
    )
    if target_matches:
        target_tie_count = current_tie_count
        source_tie_count = current_tie_count - len(target_tie_sets) + len(source_tie_sets)
    else:
        source_tie_count = current_tie_count
        target_tie_count = current_tie_count - len(source_tie_sets) + len(target_tie_sets)
    validate_tie_snapshot_indices(
        source_tie_sets, source_tie_set_indices, total_count=source_tie_count, label="source"
    )
    validate_tie_snapshot_indices(
        target_tie_sets, target_tie_set_indices, total_count=target_tie_count, label="target"
    )

    if target_matches:
        return AnalysisMutationOutcome.NO_CHANGE
    if not tie_temporal_state_matches(
        project, command.uids, source_tie_sets, source_tie_set_indices, source_states
    ):
        current_uids = {tie_set.uid for tie_set in project.model.iter_tie_sets()}
        if any(snapshot.uid not in current_uids for snapshot in source_tie_sets):
            raise HistoryApplyError(
                HistoryApplyErrorCode.TARGET_NOT_FOUND, "Tie history source target was not found."
            )
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Tie history source topology does not match storage.",
        )
    return AnalysisMutationOutcome.CHANGED


class TieSetApply:
    """Apply tie topology and parameter bindings history."""

    def __init__(
        self,
        scientific_executor: ScientificHistoryApplyExecutor,
        absorber_topology: AbsorberModelTopologyUseCase,
    ) -> None:
        """Initialize with the shared scientific executor and topology use case."""
        self._scientific_executor = scientific_executor
        self._absorber_topology = absorber_topology

    def apply(
        self,
        project: SpectroscopyProject,
        command: TieSetEditCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply tie topology and parameter bindings through one global transaction."""
        target_tie_sets = command.before_tie_sets if is_undo else command.after_tie_sets
        source_tie_sets = command.after_tie_sets if is_undo else command.before_tie_sets
        target_tie_set_indices = (
            command.before_tie_set_indices if is_undo else command.after_tie_set_indices
        )
        source_tie_set_indices = (
            command.after_tie_set_indices if is_undo else command.before_tie_set_indices
        )
        target_states = (
            command.before_component_states if is_undo else command.after_component_states
        )
        source_states = (
            command.after_component_states if is_undo else command.before_component_states
        )
        affected_component_ids = tie_history_component_ids(command)

        def mutate() -> HistoryApplyResult:
            result = command.undo(context) if is_undo else command.redo(context)
            if not result.success:
                return result
            if not tie_temporal_state_matches(
                project, command.uids, target_tie_sets, target_tie_set_indices, target_states
            ):
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    "Tie history mutation did not reach its exact target.",
                )
            return replace(result, refresh_targets=(HistoryRefreshTarget.OPTIMIZE_PANEL,))

        def rebuild() -> DomainChangeSet:
            return DomainChangeSet.of(
                *(
                    ComponentChanged(component_id=component_id)
                    for component_id in affected_component_ids
                )
            ).extend(project.model.rebuild_model_storage())

        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: preflight_tie_set_history(
                project,
                command,
                target_tie_sets=target_tie_sets,
                target_tie_set_indices=target_tie_set_indices,
                source_tie_sets=source_tie_sets,
                source_tie_set_indices=source_tie_set_indices,
                target_states=target_states,
                source_states=source_states,
            ),
            capture_runtime=lambda: self._absorber_topology.capture(project),
            mutate=mutate,
            restore_runtime=lambda snapshot: self._absorber_topology.restore(project, snapshot),
            rebuild_derived=rebuild,
            notification_scope=project.model.suppress_scientific_notifications,
        )


__all__ = [
    "TieSetApply",
    "preflight_tie_set_history",
    "tie_history_component_ids",
    "tie_temporal_state_matches",
    "validate_component_state_snapshots",
    "validate_tie_snapshot_indices",
    "validate_tie_snapshots",
]
