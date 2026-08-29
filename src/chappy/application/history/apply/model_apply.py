"""Model-component, parameter, optimize, and line-analysis history application."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

from chappy.application.analysis_artifacts import AnalysisMutationOutcome
from chappy.application.history import (
    HistoryApplyError,
    HistoryApplyErrorCode,
    HistoryRefreshTarget,
    LineAnalysisHalfWidthStateSnapshot,
    ModelComponentLinkSnapshot,
    ScientificHistoryApplyExecution,
    ScientificHistoryScope,
)
from chappy.application.history.apply import tie_set_apply
from chappy.application.history.apply.parameter_targets import (
    parameter_matches_target,
    resolve_parameter_targets,
)
from chappy.application.history.apply.runtime_state import (
    LineAnalysisHalfWidthApplySnapshot,
    restore_parameter_history,
    snapshot_parameter_history,
)
from chappy.application.history.snapshot_mapping import (
    absorber_component_snapshot,
    tie_set_snapshot,
)
from chappy.core.change_set import ChangeSet as DomainChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.events import ComponentAdded, ComponentRemoved
from chappy.core.history import OperationId

if TYPE_CHECKING:
    from chappy.application.history import (
        ComponentParameterState,
        HistoryApplyResult,
        HistoryCommandContext,
        LineAnalysisHalfWidthHistoryCommand,
        ModelComponentHistoryCommand,
        ModelOptimizeApplyCommand,
        ModelParameterEditCommand,
    )
    from chappy.application.history.scientific_apply_executor import ScientificHistoryApplyExecutor
    from chappy.application.optimize.model_topology_usecase import AbsorberModelTopologyUseCase
    from chappy.core.spectroscopy_project import SpectroscopyProject


def model_component_target_is_present(
    command: ModelComponentHistoryCommand, *, is_undo: bool
) -> bool:
    """Return whether this direction targets components being present."""
    is_add = command.op_id in {
        OperationId.MODEL_ADD,
        OperationId.MODEL_BULK_ADD,
        OperationId.MODEL_BULK_ADD_MULTIPLET,
    }
    return is_add is (not is_undo)


def model_component_temporal_presence(
    command: ModelComponentHistoryCommand, *, before: bool
) -> bool:
    """Return whether command components exist in one temporal state."""
    is_add = command.op_id in {
        OperationId.MODEL_ADD,
        OperationId.MODEL_BULK_ADD,
        OperationId.MODEL_BULK_ADD_MULTIPLET,
    }
    return (not is_add) if before else is_add


def model_component_temporal_state_matches(
    project: SpectroscopyProject, command: ModelComponentHistoryCommand, *, before: bool
) -> bool:
    """Compare runtime storage with one exact command temporal state."""
    present = model_component_temporal_presence(command, before=before)
    components_match = True
    for snapshot, expected_index in zip(
        command.components, command.component_indices, strict=True
    ):
        current = project.model.get_component_by_id(snapshot.component_id)
        if present:
            components_match = components_match and (
                isinstance(current, AbsorberComponent)
                and project.model.components.index(current) == expected_index
                and absorber_component_snapshot(current) == snapshot
            )
        else:
            components_match = components_match and current is None

    component_ids = {snapshot.component_id for snapshot in command.components}
    actual_links = tuple(
        sorted(
            (line.line_id, component_id, index)
            for line in project.absorption_lines.values()
            for index, component_id in enumerate(line.model_ids)
            if component_id in component_ids
        )
    )
    expected_links = tuple(
        sorted((link.line_id, link.component_id, link.index) for link in command.links)
    )
    links_match = actual_links == expected_links if present else not actual_links
    affected_uids = {
        snapshot.uid for snapshot in (*command.tie_sets_before, *command.tie_sets_after)
    }
    expected_ties = command.tie_sets_before if before else command.tie_sets_after
    expected_indices = command.tie_set_indices_before if before else command.tie_set_indices_after
    current_ties = tuple(
        (tie_set.uid, tie_set_snapshot(tie_set), index)
        for index, tie_set in enumerate(project.model.iter_tie_sets())
        if tie_set.uid in affected_uids
    )
    expected_ties_by_uid = {
        snapshot.uid: (snapshot, index)
        for snapshot, index in zip(expected_ties, expected_indices, strict=True)
    }
    current_ties_by_uid = {uid: (snapshot, index) for uid, snapshot, index in current_ties}
    ties_match = (
        len(current_ties) == len(current_ties_by_uid)
        and current_ties_by_uid == expected_ties_by_uid
    )
    return components_match and links_match and ties_match


def preflight_model_component_history(
    project: SpectroscopyProject, command: ModelComponentHistoryCommand, *, is_undo: bool
) -> AnalysisMutationOutcome:
    """Validate exact absorber snapshots, links, tie topology, and order."""
    component_ids = tuple(snapshot.component_id for snapshot in command.components)
    if not component_ids or len(set(component_ids)) != len(component_ids):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Model component history identities must be non-empty and unique.",
        )
    if len(command.component_indices) != len(component_ids) or len(
        set(command.component_indices)
    ) != len(command.component_indices):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Model component history indices must match unique component snapshots.",
        )
    final_count = len(project.model.components) + sum(
        project.model.get_component_by_id(component_id) is None for component_id in component_ids
    )
    if any(index < 0 or index >= final_count for index in command.component_indices):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Model component history insertion index is out of bounds.",
        )

    for snapshot in command.components:
        names = tuple(parameter.name for parameter in snapshot.parameters)
        if not names or len(set(names)) != len(names):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Model component parameter identities are invalid: {snapshot.component_id}",
            )
        for parameter in snapshot.parameters:
            if (
                parameter.min_value > parameter.max_value
                or not parameter.min_value <= parameter.value <= parameter.max_value
                or not math.isfinite(parameter.value)
            ):
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    f"Model component parameter snapshot is invalid: "
                    f"{snapshot.component_id}.{parameter.name}",
                )

    link_keys = tuple((link.line_id, link.component_id) for link in command.links)
    if len(set(link_keys)) != len(link_keys):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE, "Model component history links must be unique."
        )
    links_by_line: dict[str, list[ModelComponentLinkSnapshot]] = {}
    for link in command.links:
        line = project.absorption_lines.get(link.line_id)
        if line is None:
            raise HistoryApplyError(
                HistoryApplyErrorCode.TARGET_NOT_FOUND,
                f"Model component history line not found: {link.line_id}",
            )
        if link.component_id not in component_ids or link.index < 0:
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Model component history link is invalid: {link.line_id}",
            )
        links_by_line.setdefault(link.line_id, []).append(link)
    for line_id, links in links_by_line.items():
        line = project.absorption_lines[line_id]
        final_link_count = len(line.model_ids) + sum(
            link.component_id not in line.model_ids for link in links
        )
        if any(link.index >= final_link_count for link in links):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Model component history line index is out of bounds: {line_id}",
            )

    for snapshots in (command.tie_sets_before, command.tie_sets_after):
        tie_set_apply.validate_tie_snapshots(
            project, snapshots, additional_component_ids=frozenset(component_ids)
        )
    target_is_before = is_undo
    source_tie_sets = command.tie_sets_after if target_is_before else command.tie_sets_before
    source_tie_set_indices = (
        command.tie_set_indices_after if target_is_before else command.tie_set_indices_before
    )
    target_tie_sets = command.tie_sets_before if target_is_before else command.tie_sets_after
    target_tie_set_indices = (
        command.tie_set_indices_before if target_is_before else command.tie_set_indices_after
    )
    current_tie_count = len(tuple(project.model.iter_tie_sets()))
    target_matches = model_component_temporal_state_matches(
        project, command, before=target_is_before
    )
    if target_matches:
        target_tie_count = current_tie_count
        source_tie_count = current_tie_count - len(target_tie_sets) + len(source_tie_sets)
    else:
        source_tie_count = current_tie_count
        target_tie_count = current_tie_count - len(source_tie_sets) + len(target_tie_sets)
    tie_set_apply.validate_tie_snapshot_indices(
        source_tie_sets, source_tie_set_indices, total_count=source_tie_count, label="source"
    )
    tie_set_apply.validate_tie_snapshot_indices(
        target_tie_sets, target_tie_set_indices, total_count=target_tie_count, label="target"
    )
    if target_matches:
        return AnalysisMutationOutcome.NO_CHANGE
    if not model_component_temporal_state_matches(project, command, before=not target_is_before):
        expected_present = model_component_temporal_presence(command, before=not target_is_before)
        if expected_present and any(
            project.model.get_component_by_id(component_id) is None
            for component_id in component_ids
        ):
            raise HistoryApplyError(
                HistoryApplyErrorCode.TARGET_NOT_FOUND,
                "Model component history source component was not found.",
            )
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Model component history source topology does not match storage.",
        )
    return AnalysisMutationOutcome.CHANGED


def preflight_parameter_history(
    project: SpectroscopyProject,
    component_ids: tuple[str, ...],
    states: tuple[ComponentParameterState, ...],
) -> AnalysisMutationOutcome:
    """Validate all parameter targets and report whether storage would change."""
    resolved = resolve_parameter_targets(project, component_ids, states)
    if all(parameter_matches_target(item) for item in resolved):
        return AnalysisMutationOutcome.NO_CHANGE
    return AnalysisMutationOutcome.CHANGED


def preflight_model_optimize_history(
    project: SpectroscopyProject, command: ModelOptimizeApplyCommand
) -> AnalysisMutationOutcome:
    """Validate both fit snapshots and always preserve entry freshness semantics."""
    if not command.component_ids or not command.before or not command.after:
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Model optimize history requires non-empty parameter targets.",
        )
    resolve_parameter_targets(project, command.component_ids, command.before)
    resolve_parameter_targets(project, command.component_ids, command.after)
    before_shape = {
        state.component_id: tuple(parameter.name for parameter in state.parameters)
        for state in command.before
    }
    after_shape = {
        state.component_id: tuple(parameter.name for parameter in state.parameters)
        for state in command.after
    }
    if before_shape != after_shape or any(not names for names in before_shape.values()):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Model optimize history before/after parameter targets must match exactly.",
        )
    return AnalysisMutationOutcome.CHANGED


def preflight_line_analysis_half_width_history(
    project: SpectroscopyProject,
    command: LineAnalysisHalfWidthHistoryCommand,
    states: tuple[LineAnalysisHalfWidthStateSnapshot, ...],
) -> AnalysisMutationOutcome:
    """Validate the entire region and every command line before mutation."""
    affected_ids = command.affected_line_ids
    before_ids = tuple(state.line_id for state in command.before)
    after_ids = tuple(state.line_id for state in command.after)
    for label, line_ids in (
        ("affected", affected_ids),
        ("before", before_ids),
        ("after", after_ids),
    ):
        if not line_ids:
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Analysis half-width history {label} line identities cannot be empty.",
            )
        if len(set(line_ids)) != len(line_ids):
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Analysis half-width history {label} line identities contain duplicates.",
            )
    if set(affected_ids) != set(before_ids) or set(affected_ids) != set(after_ids):
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Analysis half-width history affected, before, and after line identities "
            "must match exactly.",
        )
    region = project.absorption_regions.get(command.region_id)
    if region is None:
        raise HistoryApplyError(
            HistoryApplyErrorCode.TARGET_NOT_FOUND,
            f"Cannot apply analysis half-widths for missing region: {command.region_id}",
        )
    referenced_line_ids = tuple(
        dict.fromkeys(
            (
                *command.affected_line_ids,
                *(state.line_id for state in command.before),
                *(state.line_id for state in command.after),
                *region.line_ids,
            )
        )
    )
    missing_ids = [
        line_id for line_id in referenced_line_ids if line_id not in project.absorption_lines
    ]
    if missing_ids:
        raise HistoryApplyError(
            HistoryApplyErrorCode.TARGET_NOT_FOUND,
            "Cannot apply analysis half-width history for missing lines: "
            + ", ".join(missing_ids),
        )
    outside_ids = [
        line_id
        for line_id in referenced_line_ids
        if project.absorption_lines[line_id].region_id != command.region_id
    ]
    if outside_ids:
        raise HistoryApplyError(
            HistoryApplyErrorCode.INVALID_STATE,
            "Analysis half-width history lines do not belong to region "
            f"{command.region_id}: {', '.join(outside_ids)}",
        )
    for state in states:
        if not math.isfinite(state.half_width_kms) or state.half_width_kms <= 0:
            raise HistoryApplyError(
                HistoryApplyErrorCode.INVALID_STATE,
                f"Invalid analysis half-width for line {state.line_id}.",
            )
    if all(
        project.absorption_lines[state.line_id].window_kms == state.half_width_kms
        and project.absorption_lines[state.line_id].lambda_range == state.lambda_range
        for state in states
    ):
        return AnalysisMutationOutcome.NO_CHANGE
    return AnalysisMutationOutcome.CHANGED


class ModelApply:
    """Apply model-component, parameter, optimize, and line-analysis history."""

    def __init__(
        self,
        scientific_executor: ScientificHistoryApplyExecutor,
        absorber_topology: AbsorberModelTopologyUseCase,
    ) -> None:
        """Initialize with the shared scientific executor and topology use case."""
        self._scientific_executor = scientific_executor
        self._absorber_topology = absorber_topology

    def apply_component(
        self,
        project: SpectroscopyProject,
        command: ModelComponentHistoryCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply absorber component topology through one global transaction."""
        target_present = model_component_target_is_present(command, is_undo=is_undo)

        def mutate() -> HistoryApplyResult:
            result = command.undo(context) if is_undo else command.redo(context)
            if not result.success:
                return result
            if not model_component_temporal_state_matches(project, command, before=is_undo):
                raise HistoryApplyError(
                    HistoryApplyErrorCode.INVALID_STATE,
                    "Model component history mutation did not reach its exact target.",
                )
            return replace(result, refresh_targets=(HistoryRefreshTarget.OPTIMIZE_PANEL,))

        def rebuild() -> DomainChangeSet:
            topology_event = ComponentAdded if target_present else ComponentRemoved
            return DomainChangeSet.of(
                *(
                    topology_event(component_id=snapshot.component_id)
                    for snapshot in command.components
                )
            ).extend(project.model.rebuild_model_storage())

        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: preflight_model_component_history(project, command, is_undo=is_undo),
            capture_runtime=lambda: self._absorber_topology.capture(project),
            mutate=mutate,
            restore_runtime=lambda snapshot: self._absorber_topology.restore(project, snapshot),
            rebuild_derived=rebuild,
            notification_scope=project.model.suppress_scientific_notifications,
        )

    def apply_parameter(
        self,
        project: SpectroscopyProject,
        command: ModelParameterEditCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply one global parameter history transition atomically."""
        states = command.before if is_undo else command.after

        def mutate() -> HistoryApplyResult:
            result = command.undo(context) if is_undo else command.redo(context)
            if not result.success:
                return result
            return replace(result, refresh_targets=(HistoryRefreshTarget.OPTIMIZE_PANEL,))

        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: preflight_parameter_history(project, command.component_ids, states),
            capture_runtime=lambda: snapshot_parameter_history(project, states),
            mutate=mutate,
            restore_runtime=lambda snapshot: restore_parameter_history(project, snapshot),
            rebuild_derived=project.model.rebuild_model_storage,
        )

    def apply_optimize(
        self,
        project: SpectroscopyProject,
        command: ModelOptimizeApplyCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply one fit result transition without reviving old freshness."""
        states = command.before if is_undo else command.after

        def mutate() -> HistoryApplyResult:
            result = command.undo(context) if is_undo else command.redo(context)
            if not result.success:
                return result
            return replace(result, refresh_targets=(HistoryRefreshTarget.OPTIMIZE_PANEL,))

        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.all_analysis_capable(),
            preflight=lambda: preflight_model_optimize_history(project, command),
            capture_runtime=lambda: snapshot_parameter_history(project, states),
            mutate=mutate,
            restore_runtime=lambda snapshot: restore_parameter_history(project, snapshot),
            rebuild_derived=project.model.rebuild_model_storage,
        )

    def apply_line_analysis_half_width(
        self,
        project: SpectroscopyProject,
        command: LineAnalysisHalfWidthHistoryCommand,
        *,
        context: HistoryCommandContext,
        is_undo: bool,
    ) -> ScientificHistoryApplyExecution:
        """Apply one region-local scientific range transition atomically."""
        states = command.before if is_undo else command.after
        return self._scientific_executor.execute(
            project,
            ScientificHistoryScope.regions(command.region_id),
            preflight=lambda: preflight_line_analysis_half_width_history(project, command, states),
            capture_runtime=lambda: _snapshot_line_analysis_half_width_history(project, command),
            mutate=lambda: command.undo(context) if is_undo else command.redo(context),
            restore_runtime=lambda snapshot: _restore_line_analysis_half_width_history(
                project, command.region_id, snapshot
            ),
        )


def _snapshot_line_analysis_half_width_history(
    project: SpectroscopyProject, command: LineAnalysisHalfWidthHistoryCommand
) -> LineAnalysisHalfWidthApplySnapshot:
    """Capture exact line and region-range state before Undo or Redo."""
    region = project.absorption_regions.get(command.region_id)
    if region is None:
        raise HistoryApplyError(
            HistoryApplyErrorCode.TARGET_NOT_FOUND,
            f"Cannot apply analysis half-width history for missing region: {command.region_id}",
        )
    changed_line_ids = tuple(
        dict.fromkeys(
            (
                *command.affected_line_ids,
                *(state.line_id for state in command.before),
                *(state.line_id for state in command.after),
            )
        )
    )
    return LineAnalysisHalfWidthApplySnapshot(
        line_states=tuple(
            LineAnalysisHalfWidthStateSnapshot(
                line_id=line_id,
                half_width_kms=project.absorption_lines[line_id].window_kms,
                lambda_range=project.absorption_lines[line_id].lambda_range,
            )
            for line_id in changed_line_ids
        ),
        region_analysis_range=region.analysis_range,
    )


def _restore_line_analysis_half_width_history(
    project: SpectroscopyProject, region_id: str, snapshot: LineAnalysisHalfWidthApplySnapshot
) -> None:
    """Restore a failed scientific history apply without recalculating state."""
    for state in snapshot.line_states:
        line = project.absorption_lines[state.line_id]
        line.window_kms = state.half_width_kms
        line.lambda_range = state.lambda_range
    project.absorption_regions[region_id].analysis_range = snapshot.region_analysis_range


__all__ = [
    "ModelApply",
    "model_component_target_is_present",
    "model_component_temporal_presence",
    "model_component_temporal_state_matches",
    "preflight_model_component_history",
]
