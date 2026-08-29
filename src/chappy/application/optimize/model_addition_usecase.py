"""Use case for adding absorber model components to optimize targets."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Protocol

from chappy.application.optimize.models import ModelAdditionRequest, ModelAdditionResult
from chappy.core.absorption.models import UNASSIGNED_REGION_ID, AbsorptionLine
from chappy.core.absorption.multiplet_service import expand_multiplet_lines
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.constants import LIGHT_SPEED_KMS

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.absorption.models import AbsorptionRegion
    from chappy.core.atomic_data import AtomicLine, AtomicLineData
    from chappy.core.spectrum_model import SpectrumModel


class ModelAdditionProjectPort(Protocol):
    """Project operations required to add optimize model components."""

    absorption_regions: dict[str, AbsorptionRegion]
    absorption_lines: dict[str, AbsorptionLine]

    @property
    def model(self) -> SpectrumModel:
        """Return the spectrum model associated with the project."""
        ...

    def list_absorption_lines(self) -> list[AbsorptionLine]:
        """Return all absorption lines in the project."""
        ...


def model_addition_wavelength_range(line: AbsorptionLine) -> tuple[float, float] | None:
    """Return the observed wavelength bounds accepted for model addition.

    Args:
        line: Absorption line used as the target.

    Returns:
        Lower and upper observed wavelength bounds, or None for invalid input.
    """
    if line.window_kms <= 0:
        return None

    velocity_value = float(line.window_kms)
    center_wavelength = float(line.rest_wavelength) * (1.0 + float(line.center_z))
    delta_lambda = center_wavelength * velocity_value / float(LIGHT_SPEED_KMS)

    if (
        not math.isfinite(center_wavelength)
        or not math.isfinite(delta_lambda)
        or delta_lambda <= 0
    ):
        return None

    default_low = center_wavelength - delta_lambda
    default_high = center_wavelength + delta_lambda

    observed_range = line.lambda_range
    if observed_range is not None:
        obs_low, obs_high = observed_range
        if math.isfinite(obs_low) and math.isfinite(obs_high):
            if obs_high < obs_low:
                obs_low, obs_high = obs_high, obs_low
            constrained_low = max(default_low, obs_low)
            constrained_high = min(default_high, obs_high)
            if constrained_high > constrained_low:
                return (float(constrained_low), float(constrained_high))

    return (float(default_low), float(default_high))


class AddOptimizeModelComponentsUseCase:
    """Create absorber components for an absorption line and its multiplet siblings."""

    def __init__(self, atomic_data_provider: Callable[[], AtomicLineData]) -> None:
        """Initialize the use case.

        Args:
            atomic_data_provider: Provider for the atomic line repository.
        """
        self._atomic_data_provider = atomic_data_provider

    def add_components(
        self,
        project: ModelAdditionProjectPort,
        line: AbsorptionLine,
        request: ModelAdditionRequest,
    ) -> ModelAdditionResult:
        """Add model components to a project.

        Args:
            project: Project receiving the new components.
            line: Absorption line used as the model-addition target.
            request: Initial component parameter values.

        Returns:
            Added components and any created parameter tie sets.
        """
        atomic_data = self._atomic_data_provider()
        lines = self._resolve_multiplet_lines(project, line)

        created: dict[str, AbsorberComponent] = {}
        for target_line in lines:
            component = self._create_component_for_line(
                target_line, atomic_data=atomic_data, request=request
            )
            project.model.add_component_storage(component)
            target_line.model_ids.append(component.id)
            target_line.needs_optimization = True
            created[target_line.line_id] = component

        tie_sets: tuple[ParameterTieSet, ...] = ()
        if len(created) > 1:
            tie_id = f"linked-{min(target_line.line_id for target_line in lines)}"
            tie_set = ParameterTieSet(tie_id, name=f"Multiplet {tie_id}")
            for component in created.values():
                tie_set.add_component(component)
            project.model.add_tie_set(tie_set)
            tie_sets = (tie_set,)

        return ModelAdditionResult(components_by_line_id=created, tie_sets=tie_sets)

    def _resolve_multiplet_lines(
        self, project: ModelAdditionProjectPort, line: AbsorptionLine
    ) -> list[AbsorptionLine]:
        """Resolve the selected line and materialized siblings in display order."""
        region_id = line.region_id or UNASSIGNED_REGION_ID
        region = project.absorption_regions.get(region_id)
        if region is not None:
            candidates = [project.absorption_lines.get(line_id) for line_id in region.line_ids]
        else:
            candidates = list(project.list_absorption_lines())

        lines_by_id = {
            candidate.line_id: candidate for candidate in candidates if candidate is not None
        }
        lines_by_id[line.line_id] = line
        expanded_ids = expand_multiplet_lines(lines_by_id, [line.line_id])
        resolved = [lines_by_id[line_id] for line_id in expanded_ids if line_id in lines_by_id]
        resolved.sort(key=lambda line_item: line_item.rest_wavelength)
        return resolved

    def _create_component_for_line(
        self, line: AbsorptionLine, *, atomic_data: AtomicLineData, request: ModelAdditionRequest
    ) -> AbsorberComponent:
        """Create one absorber component for an absorption line."""
        atomic_line = self._find_atomic_line_for_line(line, atomic_data)
        if atomic_line is not None:
            component = AbsorberComponent.from_atomic_line(
                atomic_line,
                name=f"{atomic_line.species} {atomic_line.wavelength_angstrom:.1f}",
                column_density=request.column_density,
                b_parameter=request.b_parameter,
                redshift=request.redshift,
            )
        else:
            component = AbsorberComponent(
                name=f"{line.species} {line.rest_wavelength:.1f}",
                wavelength=line.rest_wavelength,
                column_density=request.column_density,
                b_parameter=request.b_parameter,
                redshift=request.redshift,
            )

        covering_factor = component.parameters["covering_factor"]
        covering_factor.set_value(request.covering_factor)
        covering_factor.fixed = True
        return component

    def _find_atomic_line_for_line(
        self, line: AbsorptionLine, atomic_data: AtomicLineData
    ) -> AtomicLine | None:
        """Find the atomic line represented by an absorption line."""
        if line.species and line.rest_wavelength > 0:
            return atomic_data.get_line_by_species_wavelength(line.species, line.rest_wavelength)
        return None
