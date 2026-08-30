"""Spectrum plot management module for SpectrumView."""

# mypy: disable-error-code="attr-defined,no-any-return,union-attr"
from __future__ import annotations

import contextlib
import logging
import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from chappy.core.components.absorber import AbsorberComponent
from chappy.core.masking import MaskDefinition
from chappy.gui.adapters.model_event_adapter import SpectrumModelEventAdapter
from chappy.gui.adapters.plotting import (
    MatplotlibSpectrumPlot,
    create_matplotlib_mouse_event_bridge_adapter,
)
from chappy.gui.protocols.plotting import RendererProtocol
from chappy.gui.spectrum.policy import AbsorptionMarkerScope
from chappy.presentation.spectrum import (
    AbsorptionMarkerInput,
    ModelWindowBuilder,
    SpectrumDisplayOptions,
    SpectrumPlotDisplayCommand,
    SpectrumRenderDTOAssembler,
    component_curve_color,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    import numpy as np
    from numpy.typing import NDArray

    from chappy.core.absorption.models import AbsorptionRegion
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.core.spectrum_model import SpectrumModel
    from chappy.gui.spectrum.policy import SpectrumPlotPolicy
    from chappy.plotting.overlays import AbsorptionLineRegion, IdentifyPreviewPayload
    from chappy.presentation.identify import DetectionOverlayPayload
    from chappy.presentation.spectrum import SpectrumComponentCurve, SpectrumRenderDTO
logger = logging.getLogger(__name__)


@runtime_checkable
class SpectrumPlotSurfaceProtocol(Protocol):
    """Protocol for plot widget interface."""

    def set_wavelength_range(self, xmin: float, xmax: float) -> None:
        """Set wavelength range."""
        ...

    def set_flux_range(self, ymin: float, ymax: float) -> None:
        """Set flux range."""
        ...

    def auto_range_all(self) -> None:
        """Auto-range all axes."""
        ...

    def auto_range_y(self) -> None:
        """Auto-range Y axis."""
        ...

    def refresh(self) -> None:
        """Refresh display."""
        ...

    def repaint(self) -> None:
        """Repaint display."""
        ...

    def clear_plot(self) -> None:
        """Clear all data."""
        ...

    def add_absorption_marker(self, marker: AbsorptionMarkerInput) -> None:
        """Add one absorption marker."""
        ...

    def clear_absorption_line_markers(self) -> None:
        """Clear absorption line markers."""
        ...

    def refresh_absorption_marker_labels(self) -> None:
        """Re-place component name labels for the current markers."""
        ...

    def set_selected_component_id(self, component_id: str | None) -> None:
        """Emphasise one absorber component's marker label."""
        ...

    def toggle_absorption_line_markers(self, show: bool) -> None:
        """Toggle absorption line marker visibility."""
        ...

    def apply_display_command(self, command: SpectrumPlotDisplayCommand) -> None:
        """Apply caller-owned plot display policy."""
        ...

    def set_model_spectrum(
        self, wavelength: NDArray[np.float64], flux: NDArray[np.float64]
    ) -> None:
        """Set model spectrum data."""
        ...

    def set_residual_data(self, wavelength: object, residuals: object) -> None:
        """Set residual data."""
        ...

    def clear_model(self) -> None:
        """Clear model spectrum data."""
        ...

    def set_component_profile_spectra(self, curves: tuple[SpectrumComponentCurve, ...]) -> None:
        """Render per-component profile curves."""
        ...

    def clear_component_profiles(self) -> None:
        """Clear every per-component profile curve."""
        ...

    def clear_residual(self) -> None:
        """Clear residual data."""
        ...

    def set_observed_spectrum(
        self,
        wavelength: NDArray[np.float64],
        flux: NDArray[np.float64],
        error: NDArray[np.float64] | None = None,
    ) -> None:
        """Set observed spectrum data."""
        ...

    def set_absorption_line_regions(self, regions: Sequence[AbsorptionLineRegion]) -> None:
        """Display absorption line overlays."""
        ...

    def set_detection_regions(self, regions: list[DetectionOverlayPayload]) -> None:
        """Display detection region overlays."""
        ...

    def set_identify_preview(self, preview: IdentifyPreviewPayload | None) -> None:
        """Display identify-mode preview overlays."""
        ...

    def set_mask_regions(self, masks: Iterable[MaskDefinition]) -> None:
        """Display mask region overlays."""
        ...

    def set_active_mask(self, mask_id: str | None) -> None:
        """Highlight the active mask overlay."""
        ...

    def cancel_mask_selection(self) -> None:
        """Cancel the active mask selection overlay."""
        ...

    def hide_continuum_display(self) -> None:
        """Hide continuum display overlays."""
        ...

    def ensure_continuum_reference_line(self) -> None:
        """Ensure the continuum reference line is visible."""
        ...


@runtime_checkable
class ModelResidualClearPort(Protocol):
    """Plot widget operations required to clear model and residual display."""

    def clear_model(self) -> None:
        """Clear model data from the plot."""
        ...

    def clear_residual(self) -> None:
        """Clear residual data from the plot."""
        ...


# RendererProtocol, and PlotItemProtocol are imported from protocols.plotting


@dataclass(frozen=True, slots=True)
class SpectrumPlotHostFactory:
    """Factory that builds plot hosts with explicit rendering dependencies."""

    render_dto_assembler: SpectrumRenderDTOAssembler

    def create(self, parent_view: QWidget) -> SpectrumPlotHost:
        """Create a plot host for one spectrum view."""
        return SpectrumPlotHost(parent_view, self.render_dto_assembler)


def create_default_spectrum_plot_host_factory() -> SpectrumPlotHostFactory:
    """Create the default plot host factory for GUI composition."""
    return SpectrumPlotHostFactory(SpectrumRenderDTOAssembler(ModelWindowBuilder()))


class SpectrumPlotHost(QObject):
    """Hosts spectrum plot widget and operations.

    This class handles:
    - Plot widget creation and management
    - Data display and updates
    - User interaction modes
    - Display options
    """

    absorber_selected = Signal(str)  # absorber_id
    absorber_parameter_changed = Signal(str, str, float)  # absorber_id, param_name, value

    def __init__(
        self, parent_view: QWidget, render_dto_assembler: SpectrumRenderDTOAssembler
    ) -> None:
        """Initialize the plot host.

        Args:
            parent_view: Parent spectrum view widget
            render_dto_assembler: DTO assembler for model and residual rendering.
        """
        super().__init__(parent_view)

        self.parent_view = parent_view
        self.plot_widget: SpectrumPlotSurfaceProtocol | None = None

        # State tracking
        self._updating_plot = False
        self._pending_detection_regions: list[DetectionOverlayPayload] = []
        self._pending_line_regions: list[AbsorptionLineRegion] = []
        self._identify_preview_payload: IdentifyPreviewPayload | None = None
        self._pending_mask_definitions: list[MaskDefinition] = []

        # Display policy and group tracking for model/residual display control
        self._plot_mode_policy: SpectrumPlotPolicy | None = None
        self._selected_absorption_region: AbsorptionRegion | None = None
        self._active_mask_group: str | None = None
        self._selected_component_id: str | None = None
        self._base_display_command = SpectrumPlotDisplayCommand(
            use_normalized_observed=False, render_absorption_line_labels=True
        )
        self._display_options = SpectrumDisplayOptions()
        self._display_command = self._effective_display_command()

        self._project_context: SpectroscopyProject | None = None
        self._attached_model: SpectrumModel | None = None
        self._model_event_adapter: SpectrumModelEventAdapter | None = None
        self._render_dto_assembler = render_dto_assembler
        self._tie_label_resolver: Callable[[AbsorberComponent], str | None] | None = None

    def _effective_display_command(self) -> SpectrumPlotDisplayCommand:
        """Combine the policy-owned command with the user display toggles."""
        policy = self._plot_mode_policy
        return replace(
            self._base_display_command,
            show_error_spectrum=self._display_options.show_error_spectrum,
            show_component_profiles=(
                self._display_options.show_component_profiles
                and (policy is None or policy.show_model_and_residual)
            ),
        )

    @property
    def display_command(self) -> SpectrumPlotDisplayCommand:
        """Return the display command currently applied to the plot surface."""
        return self._display_command

    def apply_display_options(self, options: SpectrumDisplayOptions) -> None:
        """Apply user display toggles and refresh the affected curves."""
        self._display_options = options
        self._display_command = self._effective_display_command()
        if self.plot_widget is None:
            return
        self.plot_widget.apply_display_command(self._display_command)
        if self._project_context is not None:
            self.update_model_components(self._project_context)
            self.update_absorption_line_markers(self._project_context)

    def set_tie_label_resolver(
        self, resolver: Callable[[AbsorberComponent], str | None] | None
    ) -> None:
        """Set the resolver used to append tie labels to absorption marker text."""
        self._tie_label_resolver = resolver

    def create_widget(self) -> QWidget:
        """Create and return the plot widget.

        Returns:
            The plot widget
        """
        # Pass parent_view to MatplotlibSpectrumPlot constructor
        # MatplotlibSpectrumPlot implements the SpectrumPlotSurfaceProtocol interface
        plot_widget = MatplotlibSpectrumPlot(
            parent=self.parent_view,
            mouse_event_bridge_factory=create_matplotlib_mouse_event_bridge_adapter,
        )
        self.plot_widget = plot_widget  # type: ignore[assignment]
        plot_widget.apply_display_command(self._display_command)
        plot_widget.set_selected_component_id(self._selected_component_id)

        # Connect signals
        self.setup_plot_connections()

        if self._pending_detection_regions:
            plot_widget.set_detection_regions(self._pending_detection_regions)

        if self._pending_line_regions:
            plot_widget.set_absorption_line_regions(tuple(self._pending_line_regions))

        if self._identify_preview_payload:
            plot_widget.set_identify_preview(self._identify_preview_payload)

        if self._pending_mask_definitions:
            plot_widget.set_mask_regions(self._pending_mask_definitions)

        return plot_widget

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Attach project context and listen for mask updates."""
        self._detach_model()
        self._project_context = project

        if project is not None:
            model = project.model
            self._attached_model = model
            self._model_event_adapter = SpectrumModelEventAdapter(model, self)
            self._model_event_adapter.masks_changed.connect(self._handle_masks_changed)
            self.update_mask_regions(model.mask_definitions)
        else:
            self.update_mask_regions([])

    def _detach_model(self) -> None:
        if self._model_event_adapter is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self._model_event_adapter.masks_changed.disconnect(self._handle_masks_changed)
            self._model_event_adapter.close()
            self._model_event_adapter = None
        self._attached_model = None

    def _handle_masks_changed(self) -> None:
        if self._attached_model is None:
            return
        self.update_mask_regions(self._attached_model.mask_definitions)

    def setup_plot_connections(self) -> None:
        """Setup plot signal connections."""
        if not self.plot_widget:
            return

    def apply_policy(self, policy: SpectrumPlotPolicy) -> None:
        """Apply caller-owned neutral plot display policy."""
        self._plot_mode_policy = policy
        self._base_display_command = policy.display_command
        self._display_command = self._effective_display_command()

        if not policy.show_mask_regions:
            if self._active_mask_group is not None:
                self._active_mask_group = None
            self.update_mask_regions([])

        if not policy.show_model_and_residual and self.plot_widget:
            self._clear_model_and_residual()
        elif policy.show_model_and_residual and self._selected_absorption_region:
            project = self._require_project_context()
            self.update_model_components(project)

        if policy.show_absorption_line_markers and self.plot_widget is not None:
            self._rebuild_absorption_line_markers()

        if not self.plot_widget:
            return

        self.plot_widget.apply_display_command(self._display_command)
        self.plot_widget.toggle_absorption_line_markers(show=policy.show_absorption_line_markers)

    def preflight_policy(self, policy: SpectrumPlotPolicy) -> None:
        """Validate policy prerequisites without changing plot state."""
        model_context_required = (
            policy.show_model_and_residual and self._selected_absorption_region is not None
        )
        if model_context_required and self._project_context is None:
            self._require_project_context()

    def invalidate_policy(self) -> None:
        """Mark plot policy unknown after an unrecoverable transition failure."""
        self._plot_mode_policy = None

    def update_from_project(self, project: SpectroscopyProject) -> None:
        """Update plot from project data.

        This method is called by the coordinator when project state changes.

        Args:
            project: Project containing data to display
        """
        if not project:
            self.clear_plot_data()
            return

        # Update observed data
        self.update_plot_data(project)

        # Update model components
        self.update_model_components(project)

        # Update absorption line markers
        self.update_absorption_line_markers(project)

        # Update mask overlays
        self.update_mask_regions(project.model.mask_definitions)

    def update_plot_data(self, project: SpectroscopyProject) -> None:
        """Update plot with spectrum data from project.

        Args:
            project: Project containing spectrum data
        """
        if self.plot_widget is None:
            msg = "Plot widget is required before updating plot data."
            raise RuntimeError(msg)

        if self._updating_plot:
            return

        self._updating_plot = True
        try:
            spectrum = project.model.observed_spectrum
            if spectrum is None:
                return

            self.plot_widget.set_observed_spectrum(
                spectrum.wavelength, spectrum.flux, spectrum.error
            )
            self.plot_widget.apply_display_command(self._display_command)
        finally:
            self._updating_plot = False

    def update_model_components(self, project: SpectroscopyProject) -> None:
        """Update plot with model components from project.

        Only displays model and residual when the caller-owned plot policy
        enables it, and only within the selected absorption line group.

        Args:
            project: Project containing model components
        """
        if self.plot_widget is None:
            msg = "Plot widget is required before updating model components."
            raise RuntimeError(msg)

        if self._plot_mode_policy is None or not self._plot_mode_policy.show_model_and_residual:
            self._clear_model_and_residual()
            return

        # Check if there's a selected absorption region
        if not self._selected_absorption_region:
            self._clear_model_and_residual()
            return

        model = project.model

        render_dto = self._build_render_dto(project, self._selected_absorption_region)
        if not render_dto.windows:
            self._clear_model_and_residual()
            return

        if not model.is_model_valid:
            model.update_model()

        self._render_model_residual_dto(render_dto)

    def refresh_selected_region_model_residual(self, region_id: str) -> bool:
        """Re-slice selected-region curves from existing model data only.

        This scoped display refresh deliberately does not invalidate or update the
        scientific model. It is used when only wavelength analysis windows change.

        Returns:
            True when the selected region matched and its curves were refreshed.
        """
        selected_region = self._selected_absorption_region
        if selected_region is None or selected_region.region_id != region_id:
            return False
        if self._plot_mode_policy is None or not self._plot_mode_policy.show_model_and_residual:
            return False
        if self.plot_widget is None:
            msg = "Plot widget is required before refreshing selected-region curves."
            raise RuntimeError(msg)

        project = self._require_project_context()
        render_dto = self._build_render_dto(project, selected_region)
        self._render_model_residual_dto(render_dto)
        return True

    def _build_render_dto(
        self, project: SpectroscopyProject, region: AbsorptionRegion
    ) -> SpectrumRenderDTO:
        """Assemble the render DTO for one region under the current display toggles."""
        return self._render_dto_assembler.build(
            project,
            region,
            include_component_curves=self._display_command.show_component_profiles,
            emphasized_component_id=self._selected_component_id,
            allowed_component_ids=self._allowed_component_ids(project),
        )

    def _allowed_component_ids(self, project: SpectroscopyProject) -> frozenset[str] | None:
        """Return the component scope selected by the active plot policy."""
        policy = self._plot_mode_policy
        if policy is None or policy.absorption_marker_scope is AbsorptionMarkerScope.ALL_REGIONS:
            return None
        selected_region = self._selected_absorption_region
        if selected_region is None:
            return frozenset()
        region_id = selected_region.region_id
        return frozenset(project.region_model_ids(region_id))

    def _render_model_residual_dto(self, render_dto: SpectrumRenderDTO) -> None:
        """Render one already-assembled model/residual DTO without model mutation."""
        plot_widget = self.plot_widget
        if plot_widget is None:
            msg = "Plot widget is required before rendering model components."
            raise RuntimeError(msg)
        if not render_dto.windows:
            self._clear_model_and_residual()
            return

        if render_dto.has_model:
            if render_dto.model_wavelength is None or render_dto.model_flux is None:
                msg = "SpectrumRenderDTO.has_model requires model wavelength and flux."
                raise RuntimeError(msg)
            plot_widget.set_model_spectrum(render_dto.model_wavelength, render_dto.model_flux)
        else:
            plot_widget.clear_model()

        if render_dto.has_residual:
            plot_widget.set_residual_data(
                render_dto.residual_wavelength, render_dto.residual_values
            )
        else:
            plot_widget.clear_residual()

        if render_dto.component_curves:
            plot_widget.set_component_profile_spectra(render_dto.component_curves)
        else:
            plot_widget.clear_component_profiles()

    def set_wavelength_range(self, min_wave: float, max_wave: float) -> None:
        """Set wavelength display range.

        Args:
            min_wave: Minimum wavelength
            max_wave: Maximum wavelength
        """
        self.set_plot_range(min_wave, max_wave)

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Set flux display range while preserving the current wavelength range.

        Args:
            min_flux: Minimum flux.
            max_flux: Maximum flux.
        """
        if not self.plot_widget:
            msg = "Plot widget is required before setting plot range."
            raise RuntimeError(msg)

        if isinstance(self.plot_widget, SpectrumPlotSurfaceProtocol):
            self.plot_widget.set_flux_range(min_flux, max_flux)

    def set_plot_range(
        self, xmin: float, xmax: float, ymin: float | None = None, ymax: float | None = None
    ) -> None:
        """Set plot display range.

        Args:
            xmin: Minimum x-axis value (wavelength)
            xmax: Maximum x-axis value (wavelength)
            ymin: Minimum y-axis value (flux), optional
            ymax: Maximum y-axis value (flux), optional
        """
        if not self.plot_widget:
            return

        # Set wavelength range
        if isinstance(self.plot_widget, SpectrumPlotSurfaceProtocol):
            self.plot_widget.set_wavelength_range(xmin, xmax)

            # Set flux range if provided
            if ymin is not None and ymax is not None:
                self.plot_widget.set_flux_range(ymin, ymax)

    def set_detection_regions(self, regions: list[DetectionOverlayPayload]) -> None:
        """Relay detection regions to the underlying plot widget."""
        self._pending_detection_regions = list(regions)
        if self.plot_widget:
            self.plot_widget.set_detection_regions(self._pending_detection_regions)

    def set_absorption_line_regions(self, regions: Sequence[AbsorptionLineRegion]) -> None:
        """Relay absorption line overlays to the plot widget."""
        self._pending_line_regions = list(regions)
        if self.plot_widget:
            self.plot_widget.set_absorption_line_regions(tuple(self._pending_line_regions))

    def set_identify_preview(self, preview: IdentifyPreviewPayload | None) -> None:
        """Forward identify-mode cursor preview payload to the plot widget."""
        self._identify_preview_payload = preview
        if self.plot_widget:
            self.plot_widget.set_identify_preview(self._identify_preview_payload)

    def set_continuum_visibility(self, visible: bool) -> None:
        """Toggle continuum visuals on the underlying plot widget.

        Args:
            visible: Whether continuum elements should be shown.
        """
        widget = self.plot_widget
        if widget is None:
            return

        if not visible:
            widget.hide_continuum_display()
            return

        if visible:
            widget.ensure_continuum_reference_line()

    def update_continuum_display(self) -> None:
        """Request a redraw of continuum visuals."""
        widget = self.plot_widget
        if widget is None:
            return

        widget.refresh()

    def ensure_continuum_reference_line(self) -> None:
        """Ensure the continuum reference line is visible."""
        widget = self.plot_widget
        if widget is None:
            return
        widget.ensure_continuum_reference_line()

    def has_valid_renderer(self) -> bool:
        """Check if a valid renderer is available.

        Returns:
            True if plot_widget has a RendererProtocol-compliant renderer.
        """
        if not self.plot_widget:
            return False

        renderer = self.plot_widget.renderer
        return renderer is not None and isinstance(renderer, RendererProtocol)

    def get_plot_range(self) -> tuple[float, float, float, float]:
        """Get current plot range.

        Returns:
            Tuple of (xmin, xmax, ymin, ymax)
        """
        if not self.plot_widget:
            msg = "Plot widget is required before reading plot range."
            raise RuntimeError(msg)

        renderer = self.plot_widget.renderer
        if renderer is None or not isinstance(renderer, RendererProtocol):
            msg = "Renderer is required before reading plot range."
            raise RuntimeError(msg)

        return renderer.get_range()

    def auto_range_all(self) -> None:
        """Auto-range both axes to fit all data."""
        if self.plot_widget and isinstance(self.plot_widget, SpectrumPlotSurfaceProtocol):
            self.plot_widget.auto_range_all()

    def auto_range_flux(self) -> None:
        """Auto-range flux (Y) axis to fit visible data."""
        if self.plot_widget is None:
            msg = "Plot widget is required before auto-ranging flux."
            raise RuntimeError(msg)
        self.plot_widget.auto_range_y()

    def refresh_plot(self) -> None:
        """Refresh the plot display."""
        if self.plot_widget:
            if isinstance(self.plot_widget, SpectrumPlotSurfaceProtocol):
                self.plot_widget.refresh()
            elif isinstance(self.plot_widget, QWidget):
                self.plot_widget.repaint()

    def clear_plot_data(self) -> None:
        """Clear all data from the plot."""
        if self.plot_widget and isinstance(self.plot_widget, SpectrumPlotSurfaceProtocol):
            self.plot_widget.clear_plot()

    def add_absorption_marker(self, marker: AbsorptionMarkerInput) -> None:
        """Add one absorption marker to the plot."""
        if self.plot_widget:
            self.plot_widget.add_absorption_marker(marker)

    def update_absorption_line_markers(self, project: SpectroscopyProject) -> None:
        """Update absorption line markers based on current project.

        Args:
            project: Project containing absorber components
        """
        if not self.plot_widget or not project:
            return

        self.clear_absorption_line_markers()

        allowed_component_ids = self._allowed_component_ids(project)
        colorize = self._display_command.show_component_profiles
        enabled_index = 0
        for component in project.model.components:
            if not isinstance(component, AbsorberComponent):
                continue

            rest_wavelength = self._required_finite_value(
                component.wavelength, component=component, field="wavelength"
            )
            redshift = self._required_parameter_value(component, "redshift")
            column_density = self._required_parameter_value(component, "column_density")
            b_parameter = self._required_parameter_value(component, "b_parameter")
            oscillator_strength = self._required_finite_value(
                component.oscillator_strength, component=component, field="oscillator_strength"
            )
            gamma = self._required_finite_value(
                component.gamma, component=component, field="gamma"
            )

            tie_label = (
                self._tie_label_resolver(component)
                if self._tie_label_resolver is not None
                else None
            )

            color: str | None = None
            if component.enabled:
                if colorize:
                    color = component_curve_color(enabled_index)
                enabled_index += 1

            marker = AbsorptionMarkerInput(
                name=component.name,
                rest_wavelength=rest_wavelength,
                redshift=redshift,
                column_density=column_density,
                b_parameter=b_parameter,
                oscillator_strength=oscillator_strength,
                gamma=gamma,
                component_id=component.id,
                tie_label=tie_label,
                color=color,
            )

            if allowed_component_ids is None or component.id in allowed_component_ids:
                self.add_absorption_marker(marker)

        self.plot_widget.refresh_absorption_marker_labels()
        show = (
            self._plot_mode_policy is None or self._plot_mode_policy.show_absorption_line_markers
        )
        self.plot_widget.toggle_absorption_line_markers(show=show)

    def _rebuild_absorption_line_markers(self) -> None:
        """Rebuild markers from the attached project or clear the empty-project layer."""
        project = self._project_context
        if project is None:
            self.clear_absorption_line_markers()
            return
        self.update_absorption_line_markers(project)

    @staticmethod
    def _required_parameter_value(component: AbsorberComponent, parameter_name: str) -> float:
        """Return a required finite absorber parameter value."""
        parameter = component.parameters.get(parameter_name)
        if parameter is None:
            msg = (
                f"Absorber component {component.id} is missing required "
                f"marker parameter: {parameter_name}"
            )
            raise RuntimeError(msg)
        return SpectrumPlotHost._required_finite_value(
            parameter.value, component=component, field=parameter_name
        )

    @staticmethod
    def _required_finite_value(value: float, *, component: AbsorberComponent, field: str) -> float:
        """Return a required finite absorber marker value."""
        resolved = float(value)
        if not math.isfinite(resolved):
            msg = f"Absorber component {component.id} has invalid marker value: {field}"
            raise ValueError(msg)
        return resolved

    def clear_absorption_line_markers(self) -> None:
        """Clear all absorption line markers from plot."""
        if self.plot_widget is None:
            msg = "Plot widget is required before clearing absorption line markers."
            raise RuntimeError(msg)
        self.plot_widget.clear_absorption_line_markers()

    def update_mask_regions(self, masks: Iterable[MaskDefinition]) -> None:
        """Update shaded mask regions displayed on the plot."""
        definitions = [mask for mask in masks if isinstance(mask, MaskDefinition)]
        if self._plot_mode_policy is None or not self._plot_mode_policy.show_mask_regions:
            definitions = []
        elif self._active_mask_group is not None:
            definitions = [
                mask for mask in definitions if mask.group_id == self._active_mask_group
            ]
        else:
            definitions = []
        self._pending_mask_definitions = definitions

        if not self.plot_widget:
            return

        self.plot_widget.set_mask_regions(definitions)

    def highlight_mask(self, mask_id: str | None) -> None:
        """Highlight a specific mask region on the plot.

        Args:
            mask_id: Identifier of the mask to emphasize, or ``None`` to clear.
        """
        if not self.plot_widget:
            msg = "Plot widget is required before highlighting mask regions."
            raise RuntimeError(msg)
        self.plot_widget.set_active_mask(mask_id)

    def cancel_mask_selection(self) -> None:
        """Cancel any interactive mask selection in the plot widget."""
        if not self.plot_widget:
            msg = "Plot widget is required before cancelling mask selection."
            raise RuntimeError(msg)
        self.plot_widget.cancel_mask_selection()

    def set_active_mask_group(self, group_id: str | None) -> None:
        """Set which mask group should be displayed during optimization.

        Args:
            group_id: Identifier of the group to activate, or ``None`` to show none.
        """
        if self._active_mask_group == group_id:
            return
        self._active_mask_group = group_id
        if self._attached_model is not None:
            self.update_mask_regions(self._attached_model.mask_definitions)

    def set_selected_component_id(self, component_id: str | None) -> None:
        """Record and forward the absorber component whose marker label is emphasised.

        Args:
            component_id: Identifier of the component to emphasise, or ``None`` to clear.
        """
        self._selected_component_id = component_id
        if self.plot_widget:
            self.plot_widget.set_selected_component_id(component_id)

    def toggle_absorption_line_markers(self, show: bool) -> None:
        """Toggle visibility of absorption line markers.

        Args:
            show: Whether to show markers
        """
        if not self.plot_widget:
            return

        if show:
            project = self._require_project_context()
            self.update_absorption_line_markers(project)

        self.plot_widget.toggle_absorption_line_markers(show)

    def set_selected_absorption_region(self, region: AbsorptionRegion | None) -> None:
        """Set the selected absorption region for model/residual display.

        Args:
            region: The selected absorption region, or None to clear
        """
        self._selected_absorption_region = region
        self._active_mask_group = region.region_id if region is not None else None

        if self._plot_mode_policy is not None and self._plot_mode_policy.show_model_and_residual:
            project = self._require_project_context()
            self.update_model_components(project)
        if (
            self._plot_mode_policy is not None
            and self._plot_mode_policy.show_absorption_line_markers
        ):
            project = self._require_project_context()
            self.update_absorption_line_markers(project)
        if self._attached_model is not None:
            self.update_mask_regions(self._attached_model.mask_definitions)

    def _require_project_context(self) -> SpectroscopyProject:
        """Return the attached project context required for model-backed rendering."""
        if self._project_context is None:
            msg = "SpectrumPlotHost requires an attached project context."
            raise RuntimeError(msg)
        return self._project_context

    def _clear_model_and_residual(self) -> None:
        """Clear model and residual display from the plot."""
        plot_widget = self.plot_widget
        if plot_widget is None:
            msg = "Plot widget is required before clearing model and residual display."
            raise RuntimeError(msg)

        if not isinstance(plot_widget, ModelResidualClearPort):
            msg = "Plot widget must implement ModelResidualClearPort."
            raise TypeError(msg)

        plot_widget.clear_model()
        plot_widget.clear_residual()
