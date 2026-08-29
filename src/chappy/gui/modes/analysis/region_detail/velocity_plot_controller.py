"""Optimize-mode velocity plot workflow controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.absorption.multiplet_service import materialized_tie_group_key
from chappy.core.absorption_display import group_lines_by_multiplet, sort_lines_for_display
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.core.editing_mode import EditingMode

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.spectroscopy_project import SpectroscopyProject


@dataclass(frozen=True, slots=True)
class OptimizeVelocityComponentContext:
    """Component marker rendered in an optimize velocity slice."""

    component_id: str
    velocity: float
    rest_wavelength: float
    label: str


@dataclass(frozen=True, slots=True)
class OptimizeVelocitySliceContext:
    """Single absorption line slice for an optimize velocity overlay."""

    rest_wavelength: float
    label: str
    center_z: float
    line_id: str
    region_id: str | None
    analysis_half_width_kms: float
    components: tuple[OptimizeVelocityComponentContext, ...]
    tie_group_key: str = ""


@dataclass(frozen=True, slots=True)
class OptimizeVelocityOverlayContext:
    """Mode-local context required to display an optimize velocity overlay."""

    region_id: str
    center_z: float
    rest_wavelength: float
    observed_wavelength: float
    species_label: str
    slices: tuple[OptimizeVelocitySliceContext, ...]


@dataclass(frozen=True, slots=True)
class OptimizeVelocityPlotPorts:
    """Shell callbacks required by the optimize velocity plot controller."""

    current_mode_provider: Callable[[], EditingMode | None]
    project_provider: Callable[[], SpectroscopyProject | None]
    selected_region_id_provider: Callable[[], str | None]
    velocity_visible_provider: Callable[[], bool]
    show_velocity_plot_callback: Callable[[OptimizeVelocityOverlayContext], None]
    hide_velocity_plot_callback: Callable[[], None]
    action_checked_callback: Callable[[bool], None]


class OptimizeVelocityPlotController:
    """Coordinate optimize velocity plot show, hide, and refresh workflows."""

    def __init__(self, ports: OptimizeVelocityPlotPorts) -> None:
        """Initialize the controller.

        Args:
            ports: Shell callbacks for project state, spectrum rendering, and actions.
        """
        self._ports = ports

    def toggle(self) -> None:
        """Toggle the optimize-mode velocity plot."""
        if self._ports.current_mode_provider() is not EditingMode.ANALYSIS:
            return

        if self._ports.velocity_visible_provider():
            self.hide()
            return

        self.refresh()

    def refresh(self) -> None:
        """Rebuild the optimize velocity plot from the selected region."""
        if self._ports.current_mode_provider() is not EditingMode.ANALYSIS:
            return

        context = self.build_context()
        if context is None:
            self.hide()
            return

        self._ports.show_velocity_plot_callback(context)
        self._ports.action_checked_callback(True)

    def hide(self) -> None:
        """Hide the optimize velocity plot."""
        self._ports.hide_velocity_plot_callback()
        self._ports.action_checked_callback(False)

    def refresh_if_visible(self) -> None:
        """Refresh the optimize velocity plot when it is currently visible."""
        if not self._ports.velocity_visible_provider():
            return
        self.refresh()

    def build_context(self) -> OptimizeVelocityOverlayContext | None:
        """Build an optimize velocity overlay context from the selected region."""
        project = self._ports.project_provider()
        region_id = self._ports.selected_region_id_provider()
        if project is None or not region_id:
            return None

        absorption_region = project.absorption_regions.get(region_id)
        if absorption_region is None or not absorption_region.line_ids:
            return None

        lines = [
            line
            for line_id in absorption_region.line_ids
            if (line := project.find_absorption_line(line_id)) is not None
        ]
        if not lines:
            return None

        sorted_lines = sort_lines_for_display(lines)
        multiplet_groups = group_lines_by_multiplet(sorted_lines)
        ordered_lines = [line for group in multiplet_groups for line in group]
        materialized_group_keys: dict[str, str] = {}
        for group in multiplet_groups:
            if len(group) < 2:
                continue
            group_key = materialized_tie_group_key(line.line_id for line in group)
            for line in group:
                materialized_group_keys[line.line_id] = group_key
        reference_line = ordered_lines[0]

        return OptimizeVelocityOverlayContext(
            region_id=region_id,
            center_z=reference_line.center_z,
            rest_wavelength=reference_line.rest_wavelength,
            observed_wavelength=reference_line.observed_wavelength(),
            species_label=reference_line.species,
            slices=tuple(
                OptimizeVelocitySliceContext(
                    rest_wavelength=line.rest_wavelength,
                    label=line.transition_name,
                    center_z=line.center_z,
                    line_id=line.line_id,
                    region_id=line.region_id,
                    analysis_half_width_kms=line.window_kms,
                    components=self._component_contexts(
                        project, line.model_ids, line.center_z, line.rest_wavelength
                    ),
                    tie_group_key=materialized_group_keys.get(line.line_id, ""),
                )
                for line in ordered_lines
            ),
        )

    def _component_contexts(
        self,
        project: SpectroscopyProject,
        model_ids: list[str],
        center_z: float,
        rest_wavelength: float,
    ) -> tuple[OptimizeVelocityComponentContext, ...]:
        """Return velocity marker contexts for model components."""
        components: list[OptimizeVelocityComponentContext] = []
        for model_id in model_ids:
            component = project.find_absorber_component(model_id)
            if component is None:
                continue
            z_comp = component.parameters["redshift"].value
            velocity = LIGHT_SPEED_KMS * (z_comp - center_z) / (1.0 + center_z)
            components.append(
                OptimizeVelocityComponentContext(
                    component_id=component.id,
                    velocity=velocity,
                    rest_wavelength=rest_wavelength,
                    label=component.name,
                )
            )
        return tuple(components)
