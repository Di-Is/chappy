"""Tests for model rendering behavior across spectrum plot modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtWidgets import QWidget

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.analysis.contracts import SpectrumProfile
from chappy.gui.shell.analysis_surface_ui_adapter import analysis_spectrum_policy
from chappy.gui.spectrum.spectrum_plot import SpectrumPlotHost
from chappy.gui.spectrum.velocity import VelocityDisplayRangeController
from chappy.presentation.spectrum import (
    ModelWindowBuilder,
    SpectrumPlotDisplayCommand,
    SpectrumRenderDTO,
    SpectrumRenderDTOAssembler,
)
from chappy.presentation.velocity import VelocityDisplayHalfWidth


class _PlotWidget:
    """Record plot data clearing and mode propagation."""

    def __init__(self) -> None:
        self.cleared_model_count = 0
        self.cleared_residual_count = 0
        self.component_curves: list[object] = []
        self.cleared_component_profiles = 0
        self.display_commands: list[SpectrumPlotDisplayCommand] = []
        self.observed_data: tuple[object, object, object | None] | None = None
        self.model_data: tuple[object, object] | None = None
        self.residual_data: tuple[object, object] | None = None
        self.fail_observed = False
        self.fail_model = False
        self.fail_mode = False
        self.fail_mask_regions = False
        self.fail_active_mask = False
        self.fail_cancel_mask = False

    def clear_model(self) -> None:
        """Record model curve clearing."""
        self.cleared_model_count += 1

    def clear_residual(self) -> None:
        """Record residual curve clearing."""
        self.cleared_residual_count += 1

    def set_component_profile_spectra(self, curves: object) -> None:
        """Record per-component profile curves."""
        self.component_curves.append(curves)

    def clear_component_profiles(self) -> None:
        """Record component curve clearing."""
        self.cleared_component_profiles += 1

    def apply_display_command(self, command: SpectrumPlotDisplayCommand) -> None:
        """Record propagated plot display policy."""
        if self.fail_mode:
            raise RuntimeError("mode failed")
        self.display_commands.append(command)

    def set_observed_spectrum(
        self, wavelength: object, flux: object, error: object | None = None
    ) -> None:
        """Record observed data."""
        if self.fail_observed:
            raise RuntimeError("observed failed")
        self.observed_data = (wavelength, flux, error)

    def set_model_spectrum(self, wavelength: object, flux: object) -> None:
        """Record model data."""
        if self.fail_model:
            raise RuntimeError("model failed")
        self.model_data = (wavelength, flux)

    def set_residual_data(self, wavelength: object, residuals: object) -> None:
        """Record residual data."""
        self.residual_data = (wavelength, residuals)

    def set_mask_regions(self, masks: object) -> None:
        """Accept mask regions."""
        if self.fail_mask_regions:
            raise RuntimeError("mask regions failed")

    def set_active_mask(self, mask_id: str | None) -> None:
        """Accept active mask."""
        if self.fail_active_mask:
            raise RuntimeError("active mask failed")

    def cancel_mask_selection(self) -> None:
        """Cancel mask selection."""
        if self.fail_cancel_mask:
            raise RuntimeError("cancel mask failed")

    def toggle_absorption_line_markers(self, show: bool) -> None:
        """Accept marker visibility changes."""


class _PlotWidgetWithoutClearPort:
    """Plot widget double missing the required model/residual clear port."""


class _FailingClearPlotWidget(_PlotWidget):
    """Plot widget double that fails while clearing model data."""

    def clear_model(self) -> None:
        """Fail model clearing."""
        raise RuntimeError("clear failed")


class _ModelRenderDTOAssembler:
    """Build a deterministic model DTO for plot host tests."""

    def build(
        self,
        project: SpectroscopyProject,
        region: AbsorptionRegion | None,
        *,
        include_component_curves: bool = False,
        emphasized_component_id: str | None = None,
    ) -> SpectrumRenderDTO:
        """Return model data without depending on domain line-window setup."""
        return SpectrumRenderDTO(
            windows=((999.0, 1003.0),),
            model_wavelength=np.array([1000.0, 1001.0, 1002.0]),
            model_flux=np.array([0.95, 0.9, 0.85]),
        )


@dataclass
class _DataBridge:
    """Expose project state to SpectrumPlotHost."""

    project: SpectroscopyProject | None = None


class _ParentView(QWidget):
    """Parent widget carrying a data bridge."""

    def __init__(self, project: SpectroscopyProject | None) -> None:
        super().__init__()
        self.data_bridge = _DataBridge(project)


class _RecordingPlotHost(SpectrumPlotHost):
    """SpectrumPlotHost that records model update requests."""

    def __init__(self, parent_view: QWidget) -> None:
        super().__init__(parent_view, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
        self.updated_projects: list[SpectroscopyProject] = []
        self.marker_projects: list[SpectroscopyProject] = []
        self.mask_region_updates: list[list[object]] = []

    def update_model_components(self, project: SpectroscopyProject) -> None:
        """Record model component refresh requests."""
        self.updated_projects.append(project)

    def update_absorption_line_markers(self, project: SpectroscopyProject) -> None:
        """Record marker refresh requests."""
        self.marker_projects.append(project)

    def update_mask_regions(self, masks: list[object]) -> None:
        """Record mask region updates."""
        self.mask_region_updates.append(list(masks))


@pytest.fixture
def project() -> SpectroscopyProject:
    """Create a project used by plot host tests."""
    return SpectroscopyProject(name="mode-rendering")


@pytest.fixture
def plot_host(qtbot, project: SpectroscopyProject) -> _RecordingPlotHost:
    """Create a recording plot host with a plot widget."""
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    host = _RecordingPlotHost(parent)
    host.plot_widget = _PlotWidget()
    host.set_project(project)
    return host


def _region(region_id: str = "region-1") -> AbsorptionRegion:
    """Create an absorption region."""
    return AbsorptionRegion(region_id=region_id, line_ids=[])


def _project_with_spectra() -> SpectroscopyProject:
    """Create a project with observed, model, and residual spectra."""
    project = SpectroscopyProject(name="mode-rendering")
    wavelength = np.array([1000.0, 1001.0, 1002.0])
    observed_flux = np.array([1.0, 0.9, 0.8])
    model_flux = np.array([0.95, 0.9, 0.85])
    project.model.set_observed_spectrum(Spectrum(wavelength=wavelength, flux=observed_flux))
    project.model.model_spectrum = Spectrum(wavelength=wavelength, flux=model_flux)
    project.model._model_valid = True
    return project


def test_entering_analysis_detail_with_selected_region_refreshes_model(
    plot_host: _RecordingPlotHost, project: SpectroscopyProject
) -> None:
    """Analysis Detail should refresh model and line markers for the selected region."""
    plot_host.set_selected_absorption_region(_region())

    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)

    assert plot_host.updated_projects == [project]
    assert plot_host.marker_projects == [project]
    assert plot_host.plot_widget is not None
    assert isinstance(plot_host.plot_widget, _PlotWidget)


def test_entering_analysis_overview_clears_model_and_residual(
    plot_host: _RecordingPlotHost,
) -> None:
    """Analysis Overview should clear model and residual plot data."""
    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.OVERVIEW).plot_policy)

    plot_widget = plot_host.plot_widget
    assert isinstance(plot_widget, _PlotWidget)
    assert plot_widget.cleared_model_count == 1
    assert plot_widget.cleared_residual_count == 1
    assert plot_host.updated_projects == []


def test_clear_model_and_residual_requires_plot_widget(qtbot) -> None:
    """Clearing model display requires an attached plot widget."""
    parent = _ParentView(None)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))

    with pytest.raises(RuntimeError, match="Plot widget is required"):
        plot_host._clear_model_and_residual()


def test_clear_model_and_residual_requires_clear_port(qtbot) -> None:
    """Plot widgets must expose a typed clear port."""
    parent = _ParentView(None)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_host.plot_widget = _PlotWidgetWithoutClearPort()

    with pytest.raises(TypeError, match="ModelResidualClearPort"):
        plot_host._clear_model_and_residual()


def test_clear_model_and_residual_propagates_plot_failure(qtbot) -> None:
    """Clear failures should not be logged and hidden."""
    parent = _ParentView(None)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_host.plot_widget = _FailingClearPlotWidget()

    with pytest.raises(RuntimeError, match="clear failed"):
        plot_host._clear_model_and_residual()


def test_update_plot_data_requires_plot_widget(qtbot, project: SpectroscopyProject) -> None:
    """Observed plot updates require an attached plot widget."""
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))

    with pytest.raises(RuntimeError, match="Plot widget is required"):
        plot_host.update_plot_data(project)


def test_update_plot_data_uses_project_observed_spectrum(qtbot) -> None:
    """Observed plot updates should use the typed project model path."""
    project = _project_with_spectra()
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_widget = _PlotWidget()
    plot_host.plot_widget = plot_widget
    plot_host.set_project(project)

    plot_host.update_plot_data(project)

    assert plot_widget.observed_data is not None
    assert plot_widget.observed_data[0] is project.model.observed_spectrum.wavelength
    assert plot_widget.observed_data[1] is project.model.observed_spectrum.flux


def test_update_plot_data_without_observed_spectrum_is_valid_empty(
    qtbot, project: SpectroscopyProject
) -> None:
    """No observed spectrum is a valid empty plot update."""
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_widget = _PlotWidget()
    plot_host.plot_widget = plot_widget
    plot_host.set_project(project)

    plot_host.update_plot_data(project)

    assert plot_widget.observed_data is None


def test_update_plot_data_propagates_plot_failure(qtbot) -> None:
    """Observed plot failures should not be logged and hidden."""
    project = _project_with_spectra()
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_widget = _PlotWidget()
    plot_widget.fail_observed = True
    plot_host.plot_widget = plot_widget
    plot_host.set_project(project)

    with pytest.raises(RuntimeError, match="observed failed"):
        plot_host.update_plot_data(project)


def test_update_model_components_requires_plot_widget(qtbot) -> None:
    """Model component rendering requires an attached plot widget."""
    project = _project_with_spectra()
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)
    plot_host._selected_absorption_region = _region()

    with pytest.raises(RuntimeError, match="Plot widget is required"):
        plot_host.update_model_components(project)


def test_update_model_components_propagates_plot_failure(qtbot) -> None:
    """Model plot failures should not be logged and hidden."""
    project = _project_with_spectra()
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_widget = _PlotWidget()
    plot_widget.fail_model = True
    plot_host.plot_widget = plot_widget
    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)
    plot_host._selected_absorption_region = _region()
    plot_host._render_dto_assembler = _ModelRenderDTOAssembler()
    plot_host.set_project(project)

    with pytest.raises(RuntimeError, match="model failed"):
        plot_host.update_model_components(project)


def test_scoped_region_refresh_reslices_residual_without_model_recalculation(qtbot) -> None:
    """Analysis-width changes should immediately reslice existing wavelength curves."""
    project = SpectroscopyProject(name="scoped-window-refresh")
    wavelength = np.arange(999.0, 1006.0)
    observed_flux = np.ones_like(wavelength)
    model_flux = np.linspace(0.98, 0.92, wavelength.size)
    project.model.set_observed_spectrum(Spectrum(wavelength=wavelength, flux=observed_flux))
    project.model.model_spectrum = Spectrum(wavelength=wavelength, flux=model_flux)
    project.model._residuals = observed_flux - model_flux
    project.model._model_valid = True
    line = AbsorptionLine(
        line_id="line-1",
        species="test",
        rest_wavelength=1002.0,
        center_z=0.0,
        window_kms=150.0,
        multiplet_label="",
        transition_name="test 1002",
        oscillator_strength=0.1,
        gamma_value=1e8,
        lambda_range=(1001.0, 1003.0),
        region_id="region-1",
    )
    region = AbsorptionRegion(
        region_id="region-1", line_ids=[line.line_id], analysis_range=line.lambda_range
    )
    project.absorption_lines[line.line_id] = line
    project.absorption_regions[region.region_id] = region

    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_widget = _PlotWidget()
    plot_host.plot_widget = plot_widget
    plot_host.set_project(project)
    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)
    plot_host.set_selected_absorption_region(region)

    applied_display_widths: list[VelocityDisplayHalfWidth] = []
    display_controller = VelocityDisplayRangeController(
        apply_display_half_width=applied_display_widths.append, state_changed=lambda _state: None
    )
    display_controller.activate(region.region_id, (line.window_kms,))
    display_controller.commit_manual(VelocityDisplayHalfWidth(600.0))
    display_state_before = display_controller.state

    with (
        patch.object(project.model, "invalidate_model") as invalidate_model,
        patch.object(project.model, "update_model") as update_model,
    ):
        line.lambda_range = (1000.0, 1004.0)
        region.analysis_range = line.lambda_range
        assert plot_host.refresh_selected_region_model_residual(region.region_id) is True
        assert plot_widget.residual_data is not None
        expanded_wavelength = plot_widget.residual_data[0]
        np.testing.assert_array_equal(expanded_wavelength, np.arange(1000.0, 1005.0))

        line.lambda_range = (1001.5, 1002.5)
        region.analysis_range = line.lambda_range
        assert plot_host.refresh_selected_region_model_residual(region.region_id) is True
        assert plot_widget.residual_data is not None
        shrunk_wavelength = plot_widget.residual_data[0]
        np.testing.assert_array_equal(shrunk_wavelength, np.array([1002.0]))

    invalidate_model.assert_not_called()
    update_model.assert_not_called()
    assert display_controller.state == display_state_before
    assert applied_display_widths[-1] == VelocityDisplayHalfWidth(600.0)


def test_entering_analysis_detail_without_region_does_not_refresh_model(
    plot_host: _RecordingPlotHost,
) -> None:
    """Analysis Detail without a selected region should not refresh model components."""
    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)

    assert plot_host.updated_projects == []
    assert plot_host.marker_projects == []
    plot_widget = plot_host.plot_widget
    assert isinstance(plot_widget, _PlotWidget)


def test_selecting_region_while_in_analysis_detail_refreshes_model(
    plot_host: _RecordingPlotHost, project: SpectroscopyProject
) -> None:
    """Selecting a region after entering Analysis Detail should refresh model components."""
    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)
    plot_host.updated_projects.clear()

    plot_host.set_selected_absorption_region(_region("region-2"))

    assert plot_host.updated_projects == [project]


def test_entering_analysis_detail_with_selected_region_requires_project_context(qtbot) -> None:
    """Selected-region model rendering requires explicit project context."""
    parent = _ParentView(None)
    qtbot.addWidget(parent)
    plot_host = _RecordingPlotHost(parent)
    plot_host.plot_widget = _PlotWidget()
    plot_host.set_selected_absorption_region(_region())

    with pytest.raises(RuntimeError, match="attached project context"):
        plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)


def test_mode_propagation_failure_is_not_swallowed(qtbot, project: SpectroscopyProject) -> None:
    """Plot widget mode failures should propagate."""
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_widget = _PlotWidget()
    plot_widget.fail_mode = True
    plot_host.plot_widget = plot_widget
    plot_host.set_project(project)

    with pytest.raises(RuntimeError, match="mode failed"):
        plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)


def test_mask_region_update_failure_is_not_swallowed(qtbot, project: SpectroscopyProject) -> None:
    """Mask region update failures should propagate."""
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_widget = _PlotWidget()
    plot_host.plot_widget = plot_widget
    plot_host.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL).plot_policy)
    plot_host.set_active_mask_group("group-1")
    plot_widget.fail_mask_regions = True

    with pytest.raises(RuntimeError, match="mask regions failed"):
        plot_host.update_mask_regions([])


def test_mask_highlight_requires_plot_widget(qtbot) -> None:
    """Mask highlight requires an attached plot widget."""
    parent = _ParentView(None)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))

    with pytest.raises(RuntimeError, match="highlighting mask"):
        plot_host.highlight_mask("mask-1")


def test_mask_cancel_requires_plot_widget(qtbot) -> None:
    """Mask cancellation requires an attached plot widget."""
    parent = _ParentView(None)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))

    with pytest.raises(RuntimeError, match="cancelling mask"):
        plot_host.cancel_mask_selection()


def test_showing_absorption_markers_requires_project_context(qtbot) -> None:
    """Showing markers requires explicit project context instead of parent probing."""
    parent = _ParentView(None)
    qtbot.addWidget(parent)
    plot_host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    plot_host.plot_widget = _PlotWidget()

    with pytest.raises(RuntimeError, match="attached project context"):
        plot_host.toggle_absorption_line_markers(True)
