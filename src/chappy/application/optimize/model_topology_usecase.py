"""Exact absorber model topology snapshots for atomic Optimize mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.application.history import (
    AbsorberComponentSnapshot,
    ModelComponentLinkSnapshot,
    TieSetSnapshot,
)
from chappy.application.history.snapshot_mapping import (
    absorber_component_snapshot,
    tie_set_snapshots,
)
from chappy.core.change_set import ChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.events import (
    ComponentAdded,
    ComponentChanged,
    ComponentRemoved,
    ModelInvalidated,
    ModelUpdated,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.core.components.base import ModelComponent, Parameter
    from chappy.core.components.tie_set import ParameterTieSet, TieParameterName
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.core.spectrum_model import SpectrumModelDerivedStateSnapshot


@dataclass(frozen=True, slots=True)
class AbsorberLineTopologySnapshot:
    """Exact model links and stale flag for one absorption line."""

    line_id: str
    model_ids: tuple[str, ...]
    needs_optimization: bool


@dataclass(frozen=True, slots=True)
class ParameterRuntimeSnapshot:
    """Exact value state for one parameter object retained by rollback."""

    parameter: Parameter
    value: float
    min_value: float
    max_value: float
    fixed: bool
    error: float
    unit: str | None


@dataclass(frozen=True, slots=True)
class AbsorberComponentRuntimeSnapshot:
    """Exact parameter bindings and tie ownership for one absorber object."""

    component: AbsorberComponent
    parameter_bindings: tuple[tuple[str, Parameter], ...]
    tie_set: ParameterTieSet | None
    external_continuum_name: str | None


@dataclass(frozen=True, slots=True)
class TieSetRuntimeSnapshot:
    """Exact nested topology and shared parameter bindings for one tie object."""

    tie_set: ParameterTieSet
    components: tuple[AbsorberComponent, ...]
    parent_tie: ParameterTieSet | None
    member_uids: frozenset[str]
    shared_parameters: tuple[tuple[TieParameterName, Parameter], ...]


@dataclass(frozen=True, slots=True)
class AbsorberModelTopologySnapshot:
    """Restorable absorber objects, parameters, tie sets, and line links."""

    components: tuple[AbsorberComponent, ...]
    model_component_order: tuple[ModelComponent, ...]
    component_runtime: tuple[AbsorberComponentRuntimeSnapshot, ...]
    parameter_runtime: tuple[ParameterRuntimeSnapshot, ...]
    tie_sets: tuple[TieSetRuntimeSnapshot, ...]
    lines: tuple[AbsorberLineTopologySnapshot, ...]
    derived_state: SpectrumModelDerivedStateSnapshot


@dataclass(frozen=True, slots=True)
class ModelDeletionHistorySnapshot:
    """Immutable pre-delete payload recorded after the scientific commit."""

    components: tuple[AbsorberComponentSnapshot, ...]
    component_indices: tuple[int, ...]
    links: tuple[ModelComponentLinkSnapshot, ...]
    tie_sets: tuple[TieSetSnapshot, ...]
    tie_set_indices: tuple[int, ...]


class AbsorberModelTopologyUseCase:
    """Capture and restore absorber topology around an atomic mutation."""

    def capture(
        self,
        project: SpectroscopyProject,
        *,
        additional_components: Iterable[AbsorberComponent] = (),
    ) -> AbsorberModelTopologySnapshot:
        """Capture all current absorber topology plus explicit mutation targets."""
        components_by_id = {
            component.id: component
            for component in project.model.components
            if isinstance(component, AbsorberComponent)
        }
        components_by_id.update((component.id, component) for component in additional_components)
        components = tuple(components_by_id.values())
        tie_sets = tuple(project.model.iter_tie_sets())
        parameters_by_identity = {
            id(parameter): parameter
            for component in components
            for parameter in component.parameters.values()
        }
        parameters_by_identity.update(
            (id(parameter), parameter)
            for tie_set in tie_sets
            for parameter in tie_set.shared_parameters.values()
        )
        return AbsorberModelTopologySnapshot(
            components=components,
            model_component_order=tuple(project.model.components),
            component_runtime=tuple(
                AbsorberComponentRuntimeSnapshot(
                    component=component,
                    parameter_bindings=tuple(component.parameters.items()),
                    tie_set=component.tie_set,
                    external_continuum_name=component.external_continuum_name,
                )
                for component in components
            ),
            parameter_runtime=tuple(
                ParameterRuntimeSnapshot(
                    parameter=parameter,
                    value=parameter.value,
                    min_value=parameter.min_val,
                    max_value=parameter.max_val,
                    fixed=parameter.fixed,
                    error=parameter.error,
                    unit=parameter.unit,
                )
                for parameter in parameters_by_identity.values()
            ),
            tie_sets=tuple(
                TieSetRuntimeSnapshot(
                    tie_set=tie_set,
                    components=tuple(tie_set.components),
                    parent_tie=tie_set.parent_tie,
                    member_uids=frozenset(tie_set.member_uids),
                    shared_parameters=tuple(tie_set.shared_parameters.items()),
                )
                for tie_set in tie_sets
            ),
            lines=tuple(
                AbsorberLineTopologySnapshot(
                    line_id=line.line_id,
                    model_ids=tuple(line.model_ids),
                    needs_optimization=line.needs_optimization,
                )
                for line in project.absorption_lines.values()
            ),
            derived_state=project.model.snapshot_derived_state_for_transaction(),
        )

    def capture_deletion_history(
        self, project: SpectroscopyProject, components: tuple[AbsorberComponent, ...]
    ) -> ModelDeletionHistorySnapshot:
        """Capture an immutable history payload before component deletion."""
        component_ids = {component.id for component in components}
        links: list[ModelComponentLinkSnapshot] = []
        for line in project.absorption_lines.values():
            for index, component_id in enumerate(line.model_ids):
                if component_id not in component_ids:
                    continue
                links.append(
                    ModelComponentLinkSnapshot(
                        line_id=line.line_id, component_id=component_id, index=index
                    )
                )

        ordered_tie_sets = tuple(project.model.iter_tie_sets())
        affected_tie_sets = project.model.tie_sets_for_components(list(component_ids))
        return ModelDeletionHistorySnapshot(
            components=tuple(absorber_component_snapshot(component) for component in components),
            component_indices=tuple(
                project.model.components.index(component) for component in components
            ),
            links=tuple(links),
            tie_sets=tie_set_snapshots(affected_tie_sets),
            tie_set_indices=tuple(
                ordered_tie_sets.index(tie_set) for tie_set in affected_tie_sets
            ),
        )

    def restore(
        self, project: SpectroscopyProject, snapshot: AbsorberModelTopologySnapshot
    ) -> None:
        """Restore an exact topology snapshot after a transaction failure."""
        with project.model.suppress_scientific_notifications(snapshot.components):
            project.model.restore_component_order_for_transaction(snapshot.model_component_order)
            project.model.restore_tie_set_order_for_transaction(
                tuple(state.tie_set for state in snapshot.tie_sets)
            )

            for tie_state in snapshot.tie_sets:
                tie_state.tie_set.components[:] = tie_state.components
                tie_state.tie_set.parent_tie = tie_state.parent_tie
                tie_state.tie_set.member_uids = set(tie_state.member_uids)
                tie_state.tie_set.shared_parameters = dict(tie_state.shared_parameters)

            for component_state in snapshot.component_runtime:
                component_state.component.parameters = dict(component_state.parameter_bindings)
                component_state.component.tie_set = component_state.tie_set
                component_state.component.external_continuum_name = (
                    component_state.external_continuum_name
                )

            for parameter_state in snapshot.parameter_runtime:
                parameter_state.parameter.min_val = parameter_state.min_value
                parameter_state.parameter.max_val = parameter_state.max_value
                parameter_state.parameter.set_value(parameter_state.value)
                parameter_state.parameter.fixed = parameter_state.fixed
                parameter_state.parameter.error = parameter_state.error
                parameter_state.parameter.unit = parameter_state.unit

            lines_by_id = project.absorption_lines
            if set(lines_by_id) != {line.line_id for line in snapshot.lines}:
                msg = "Absorber topology rollback line identities do not match the snapshot."
                raise ValueError(msg)
            for line_state in snapshot.lines:
                line = lines_by_id[line_state.line_id]
                line.model_ids[:] = line_state.model_ids
                line.needs_optimization = line_state.needs_optimization

            project.model.restore_derived_state_for_transaction(snapshot.derived_state)


def component_topology_change_set(
    *,
    added_ids: tuple[str, ...] = (),
    removed_ids: tuple[str, ...] = (),
    changed_ids: tuple[str, ...] = (),
) -> ChangeSet:
    """Build one consolidated post-commit component topology notification."""
    return ChangeSet.of(
        *(ComponentAdded(component_id=component_id) for component_id in added_ids),
        *(ComponentRemoved(component_id=component_id) for component_id in removed_ids),
        *(ComponentChanged(component_id=component_id) for component_id in changed_ids),
        ModelInvalidated(),
        ModelUpdated(),
    )


__all__ = [
    "AbsorberComponentRuntimeSnapshot",
    "AbsorberLineTopologySnapshot",
    "AbsorberModelTopologySnapshot",
    "AbsorberModelTopologyUseCase",
    "ModelDeletionHistorySnapshot",
    "ParameterRuntimeSnapshot",
    "TieSetRuntimeSnapshot",
    "component_topology_change_set",
]
