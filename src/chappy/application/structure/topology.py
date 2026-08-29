"""Exact runtime snapshots for absorption structure topology transactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.core.components.absorber import AbsorberComponent

if TYPE_CHECKING:
    from datetime import datetime

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.components.base import ModelComponent, Parameter
    from chappy.core.components.tie_set import ParameterTieSet, TieParameterName
    from chappy.core.masking import MaskDefinition
    from chappy.core.spectrum_model import SpectrumModel


class StructureTopologyProjectPort(Protocol):
    """Project storage required by an exact structure topology snapshot."""

    absorption_regions: dict[str, AbsorptionRegion]
    absorption_lines: dict[str, AbsorptionLine]
    model: SpectrumModel


@dataclass(frozen=True, slots=True)
class _RegionRuntimeState:
    """Mutable fields retained for one region object."""

    region: AbsorptionRegion
    line_ids: tuple[str, ...]
    display_color: str
    analysis_range: tuple[float, float] | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class _LineRuntimeState:
    """Structure-owned mutable fields retained for one line object."""

    line: AbsorptionLine
    region_id: str | None
    multiplet_ids: tuple[str, ...]
    model_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ComponentRuntimeState:
    """Mutable bindings retained for one absorber component object."""

    component: AbsorberComponent
    group_id: str | None
    parameter_bindings: tuple[tuple[str, Parameter], ...]
    tie_set: ParameterTieSet | None
    external_continuum_name: str | None


@dataclass(frozen=True, slots=True)
class _ParameterRuntimeState:
    """Mutable scalar state retained for one parameter object."""

    parameter: Parameter
    value: float
    min_value: float
    max_value: float
    fixed: bool
    error: float
    unit: str | None


@dataclass(frozen=True, slots=True)
class _TieSetRuntimeState:
    """Nested membership and bindings retained for one tie set."""

    tie_set: ParameterTieSet
    components: tuple[AbsorberComponent, ...]
    parent_tie: ParameterTieSet | None
    member_uids: frozenset[str]
    shared_parameters: tuple[tuple[TieParameterName, Parameter], ...]


@dataclass(frozen=True, slots=True)
class StructureTopologySnapshot:
    """Exact ordered object graph restored after a structure transaction abort."""

    regions: tuple[tuple[str, _RegionRuntimeState], ...]
    lines: tuple[tuple[str, _LineRuntimeState], ...]
    masks: tuple[MaskDefinition, ...]
    model_components: tuple[ModelComponent, ...]
    components: tuple[_ComponentRuntimeState, ...]
    parameters: tuple[_ParameterRuntimeState, ...]
    tie_sets: tuple[_TieSetRuntimeState, ...]


class StructureTopologySnapshotService:
    """Capture and restore topology without accessing project-private storage."""

    def capture(self, project: StructureTopologyProjectPort) -> StructureTopologySnapshot:
        """Capture mapping order, object identity, and every mutable topology field."""
        components = tuple(
            component
            for component in project.model.components
            if isinstance(component, AbsorberComponent)
        )
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
        return StructureTopologySnapshot(
            regions=tuple(
                (
                    key,
                    _RegionRuntimeState(
                        region=region,
                        line_ids=tuple(region.line_ids),
                        display_color=region.display_color,
                        analysis_range=region.analysis_range,
                        created_at=region.created_at,
                    ),
                )
                for key, region in project.absorption_regions.items()
            ),
            lines=tuple(
                (
                    key,
                    _LineRuntimeState(
                        line=line,
                        region_id=line.region_id,
                        multiplet_ids=tuple(line.multiplet_ids),
                        model_ids=tuple(line.model_ids),
                    ),
                )
                for key, line in project.absorption_lines.items()
            ),
            masks=project.model.mask_definitions,
            model_components=tuple(project.model.components),
            components=tuple(
                _ComponentRuntimeState(
                    component=component,
                    group_id=component.group_id,
                    parameter_bindings=tuple(component.parameters.items()),
                    tie_set=component.tie_set,
                    external_continuum_name=component.external_continuum_name,
                )
                for component in components
            ),
            parameters=tuple(
                _ParameterRuntimeState(
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
                _TieSetRuntimeState(
                    tie_set=tie_set,
                    components=tuple(tie_set.components),
                    parent_tie=tie_set.parent_tie,
                    member_uids=frozenset(tie_set.member_uids),
                    shared_parameters=tuple(tie_set.shared_parameters.items()),
                )
                for tie_set in tie_sets
            ),
        )

    def restore(
        self, project: StructureTopologyProjectPort, snapshot: StructureTopologySnapshot
    ) -> None:
        """Restore exact objects and order; the base executor restores derived caches."""
        with project.model.suppress_scientific_notifications(snapshot.model_components):
            for _, region_state in snapshot.regions:
                region_state.region.line_ids[:] = region_state.line_ids
                region_state.region.display_color = region_state.display_color
                region_state.region.analysis_range = region_state.analysis_range
                region_state.region.created_at = region_state.created_at
            for _, line_state in snapshot.lines:
                line_state.line.region_id = line_state.region_id
                line_state.line.multiplet_ids[:] = line_state.multiplet_ids
                line_state.line.model_ids[:] = line_state.model_ids

            project.absorption_regions.clear()
            project.absorption_regions.update(
                (key, region_state.region) for key, region_state in snapshot.regions
            )
            project.absorption_lines.clear()
            project.absorption_lines.update(
                (key, line_state.line) for key, line_state in snapshot.lines
            )

            project.model.restore_component_order_for_transaction(snapshot.model_components)
            project.model.restore_tie_set_order_for_transaction(
                tuple(state.tie_set for state in snapshot.tie_sets)
            )
            for tie_state in snapshot.tie_sets:
                tie_state.tie_set.components[:] = tie_state.components
                tie_state.tie_set.parent_tie = tie_state.parent_tie
                tie_state.tie_set.member_uids = set(tie_state.member_uids)
                tie_state.tie_set.shared_parameters = dict(tie_state.shared_parameters)
            for component_state in snapshot.components:
                component_state.component.parameters = dict(component_state.parameter_bindings)
                component_state.component.tie_set = component_state.tie_set
                component_state.component.external_continuum_name = (
                    component_state.external_continuum_name
                )
                component_state.component.set_group(component_state.group_id)
            for parameter_state in snapshot.parameters:
                parameter_state.parameter.min_val = parameter_state.min_value
                parameter_state.parameter.max_val = parameter_state.max_value
                parameter_state.parameter.set_value(parameter_state.value)
                parameter_state.parameter.fixed = parameter_state.fixed
                parameter_state.parameter.error = parameter_state.error
                parameter_state.parameter.unit = parameter_state.unit
            project.model.restore_mask_definitions_for_transaction(
                snapshot.masks, model_was_valid=False
            )


__all__ = [
    "StructureTopologyProjectPort",
    "StructureTopologySnapshot",
    "StructureTopologySnapshotService",
]
