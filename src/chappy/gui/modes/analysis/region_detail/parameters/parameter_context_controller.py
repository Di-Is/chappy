"""Controller for optimize parameter context and validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.core.absorption_display import sort_lines_for_display
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import FULL_TIE_MASK
from chappy.core.redshift_limits import calculate_dynamic_z_limits

if TYPE_CHECKING:
    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.spectroscopy_project import SpectroscopyProject


class OptimizeParameterContextController:
    """Resolve component-line context for optimize parameter workflows."""

    def __init__(self, *, multiplet_redshift_tolerance: float, min_redshift: float) -> None:
        """Initialize the controller.

        Args:
            multiplet_redshift_tolerance: Maximum redshift difference for materialized multiplets.
            min_redshift: Static lower bound used when no line-specific bounds exist.
        """
        self._multiplet_redshift_tolerance = multiplet_redshift_tolerance
        self._min_redshift = min_redshift

    def lines_for_component(
        self, project: SpectroscopyProject | None, component: AbsorberComponent | None
    ) -> list[AbsorptionLine]:
        """Return absorption lines linked to a component."""
        if project is None or not isinstance(component, AbsorberComponent):
            return []

        component_id = component.id
        if not component_id:
            return []

        return [
            line for line in project.absorption_lines.values() if component_id in line.model_ids
        ]

    def line_for_component(
        self, project: SpectroscopyProject | None, component: AbsorberComponent | None
    ) -> AbsorptionLine | None:
        """Return the first absorption line linked to a component."""
        lines = self.lines_for_component(project, component)
        return lines[0] if lines else None

    def line_display_id(
        self, project: SpectroscopyProject | None, line: AbsorptionLine | None
    ) -> int | None:
        """Return the 1-based display id for a line within its region."""
        if line is None or project is None:
            return None
        region_id = line.region_id
        if region_id is None:
            return None
        region = project.absorption_regions.get(region_id)
        if region is None:
            return None

        region_lines = [
            project.absorption_lines[line_id]
            for line_id in region.line_ids
            if line_id in project.absorption_lines
        ]
        sorted_lines = sort_lines_for_display(region_lines)
        for index, sorted_line in enumerate(sorted_lines, start=1):
            if sorted_line.line_id == line.line_id:
                return index
        return None

    def component_index(
        self, component: AbsorberComponent, line: AbsorptionLine | None
    ) -> int | None:
        """Return the 1-based component index within a line."""
        if line is None or not line.model_ids:
            return None
        try:
            return line.model_ids.index(component.id) + 1
        except ValueError:
            return None

    def z_bounds(
        self, component: AbsorberComponent, line: AbsorptionLine | None
    ) -> tuple[float, float] | None:
        """Return dynamic or static redshift bounds for a component."""
        if line is not None:
            return calculate_dynamic_z_limits(line.rest_wavelength, line.lambda_range)

        param = component.parameters.get("redshift")
        if param is None:
            return None
        return (param.min_val, param.max_val)

    def validate_value(
        self,
        project: SpectroscopyProject | None,
        param_name: str,
        value: float,
        component: AbsorberComponent,
    ) -> bool:
        """Validate a parameter value with line-specific constraints."""
        if param_name == "redshift":
            line = self.line_for_component(project, component)
            if line is not None:
                z_min, z_max = calculate_dynamic_z_limits(line.rest_wavelength, line.lambda_range)
                return z_min <= value <= z_max
            return value >= self._min_redshift

        if param_name == "column_density":
            return value >= 0
        if param_name == "b_parameter":
            return value >= 0
        if param_name == "covering_factor":
            return 0 <= value <= 1
        return True

    def collect_multiplet_components(
        self, project: SpectroscopyProject | None, component: AbsorberComponent | None
    ) -> list[AbsorberComponent]:
        """Collect components linked to the same materialized multiplet.

        Only auto-managed (``origin="multiplet"``) full-mask tie sets are treated
        as a materialized multiplet here. A user-created tie set (``origin="user"``)
        is an independent parameter-sharing arrangement, not a physical multiplet
        linkage, so its members must not be swept up by this collection (which
        feeds delete-cascade and adjust flows that assume full sharing).
        """
        if not isinstance(component, AbsorberComponent):
            return []

        tie_set = component.tie_set
        if (
            tie_set is not None
            and tie_set.origin == "multiplet"
            and tie_set.mask == FULL_TIE_MASK
            and tie_set.components
        ):
            return list(tie_set.components)

        if project is None or project.model is None:
            return [component]

        related: list[AbsorberComponent] = [component]
        seen_ids: set[str] = {component.id}

        base_lines = self.lines_for_component(project, component)
        if not base_lines:
            return related

        base_region_ids = {line.region_id for line in base_lines if line.region_id}
        reference_tokens = self._line_tokens(base_lines)

        redshift_param = component.parameters.get("redshift")
        reference_redshift = float(redshift_param.value) if redshift_param is not None else None

        for candidate in project.model.components:
            if not isinstance(candidate, AbsorberComponent):
                continue
            if candidate.id in seen_ids:
                continue

            candidate_lines = self.lines_for_component(project, candidate)
            if not candidate_lines:
                continue

            if base_region_ids and not any(
                line.region_id in base_region_ids for line in candidate_lines
            ):
                continue

            if not self._has_matching_redshift(candidate, reference_redshift):
                continue

            candidate_tokens = self._line_tokens(candidate_lines)
            if reference_tokens and reference_tokens.intersection(candidate_tokens):
                related.append(candidate)
                seen_ids.add(candidate.id)

        return related

    @staticmethod
    def _line_tokens(lines: list[AbsorptionLine]) -> set[str]:
        """Return lookup tokens derived from absorption lines."""
        tokens: set[str] = set()
        for line in lines:
            tokens.add(line.line_id)
            for token in line.multiplet_ids:
                if token:
                    tokens.add(token)
        return tokens

    def _has_matching_redshift(
        self, candidate: AbsorberComponent, reference_redshift: float | None
    ) -> bool:
        """Return whether a candidate matches the reference redshift."""
        if reference_redshift is None:
            return True

        candidate_param = candidate.parameters.get("redshift")
        if candidate_param is None:
            return False
        candidate_redshift = float(candidate_param.value)
        return abs(candidate_redshift - reference_redshift) <= self._multiplet_redshift_tolerance
