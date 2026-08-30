"""Tests for user-controlled spectrum display toggles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PySide6.QtWidgets import QWidget

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.analysis.contracts import SpectrumProfile
from chappy.gui.shell.analysis_surface_ui_adapter import analysis_spectrum_policy
from chappy.gui.spectrum.spectrum_plot import (
    SpectrumPlotHost,
    create_default_spectrum_plot_host_factory,
)
from chappy.gui.spectrum.spectrum_view import SpectrumView
from chappy.presentation.spectrum import (
    ModelWindowBuilder,
    SpectrumDisplayOptions,
    SpectrumRenderDTOAssembler,
    component_curve_color,
)

if TYPE_CHECKING:
    from chappy.presentation.spectrum import (
        AbsorptionMarkerInput,
        SpectrumComponentCurve,
        SpectrumPlotDisplayCommand,
    )


class _PlotWidget:
    """Plot surface double recording display commands, curves and markers."""

    def __init__(self) -> None:
        self.display_commands: list[SpectrumPlotDisplayCommand] = []
        self.component_curves: list[tuple[SpectrumComponentCurve, ...]] = []
        self.cleared_component_profiles = 0
        self.markers: list[AbsorptionMarkerInput] = []

    def apply_display_command(self, command: SpectrumPlotDisplayCommand) -> None:
        """Record the applied display command."""
        self.display_commands.append(command)

    def set_component_profile_spectra(self, curves: tuple[SpectrumComponentCurve, ...]) -> None:
        """Record rendered component curves."""
        self.component_curves.append(curves)

    def clear_component_profiles(self) -> None:
        """Record component curve clearing."""
        self.cleared_component_profiles += 1

    def set_model_spectrum(self, wavelength: object, flux: object) -> None:
        """Accept model data."""

    def set_residual_data(self, wavelength: object, residuals: object) -> None:
        """Accept residual data."""

    def clear_model(self) -> None:
        """Accept model clearing."""

    def clear_residual(self) -> None:
        """Accept residual clearing."""

    def add_absorption_marker(self, marker: AbsorptionMarkerInput) -> None:
        """Record one absorption marker."""
        self.markers.append(marker)

    def clear_absorption_line_markers(self) -> None:
        """Drop recorded markers."""
        self.markers.clear()

    def refresh_absorption_marker_labels(self) -> None:
        """Accept label refresh."""

    def toggle_absorption_line_markers(self, show: bool) -> None:
        """Accept marker visibility changes."""

    def set_mask_regions(self, masks: object) -> None:
        """Accept mask regions."""


class _ParentView(QWidget):
    """Parent widget carrying the data bridge the plot host expects."""

    def __init__(self, project: SpectroscopyProject) -> None:
        super().__init__()
        self.data_bridge = _DataBridge(project)


class _DataBridge:
    """Expose project state to the plot host."""

    def __init__(self, project: SpectroscopyProject) -> None:
        self.project = project


def _project() -> tuple[SpectroscopyProject, AbsorptionRegion]:
    """Create a project with a selected region and two enabled absorbers."""
    project = SpectroscopyProject(name="display-options")
    wavelength = np.linspace(4640.0, 4650.0, 200, dtype=np.float64)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength))
    )
    project.model.add_component(
        AbsorberComponent(component_id="abs-1", wavelength=1548.195, redshift=2.0)
    )
    project.model.add_component(
        AbsorberComponent(component_id="abs-2", wavelength=1550.77, redshift=2.0)
    )
    project.absorption_lines["line-1"] = AbsorptionLine(
        line_id="line-1",
        species="C IV",
        rest_wavelength=1548.195,
        center_z=2.0,
        window_kms=500.0,
        multiplet_label="",
        transition_name="C IV 1548.2",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
        lambda_range=(4640.0, 4650.0),
        model_ids=["abs-1", "abs-2"],
    )
    region = AbsorptionRegion(region_id="region-1", line_ids=["line-1"])
    project.absorption_regions[region.region_id] = region
    return project, region


@dataclass(frozen=True)
class _Harness:
    """A plot host wired to a recording plot surface and its project."""

    host: SpectrumPlotHost
    widget: _PlotWidget
    project: SpectroscopyProject


def _harness(qtbot, profile: SpectrumProfile) -> _Harness:
    """Create a plot host with a selected region under one spectrum profile."""
    project, region = _project()
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    widget = _PlotWidget()
    host.plot_widget = widget
    host.set_project(project)
    host.set_selected_absorption_region(region)
    host.apply_policy(analysis_spectrum_policy(profile).plot_policy)
    return _Harness(host=host, widget=widget, project=project)


@pytest.fixture
def region_detail(qtbot) -> _Harness:
    """Create a plot host in region-detail policy, where model display is supported."""
    return _harness(qtbot, SpectrumProfile.REGION_DETAIL)


def test_display_command_defaults_to_error_curve_without_component_curves(
    region_detail: _Harness,
) -> None:
    """The error curve stays visible and component curves stay off until requested."""
    assert region_detail.host.display_command.show_error_spectrum is True
    assert region_detail.host.display_command.show_component_profiles is False


def test_hiding_the_error_curve_reaches_the_plot_surface(region_detail: _Harness) -> None:
    """The error toggle is delivered through the display command."""
    region_detail.host.apply_display_options(SpectrumDisplayOptions(show_error_spectrum=False))

    assert region_detail.host.display_command.show_error_spectrum is False
    assert region_detail.widget.display_commands[-1].show_error_spectrum is False


def test_enabling_component_curves_renders_one_curve_per_absorber(region_detail: _Harness) -> None:
    """Turning component curves on renders them without another explicit refresh."""
    region_detail.host.apply_display_options(SpectrumDisplayOptions(show_component_profiles=True))

    curves = region_detail.widget.component_curves[-1]
    assert [curve.component_id for curve in curves] == ["abs-1", "abs-2"]


def test_disabling_component_curves_clears_them(region_detail: _Harness) -> None:
    """Turning the toggle back off removes the rendered component curves."""
    region_detail.host.apply_display_options(SpectrumDisplayOptions(show_component_profiles=True))

    region_detail.host.apply_display_options(SpectrumDisplayOptions(show_component_profiles=False))

    assert region_detail.widget.cleared_component_profiles > 0


def test_component_curves_stay_off_where_the_model_is_not_shown(qtbot) -> None:
    """A policy without model display wins over the user's component-curve toggle."""
    overview = _harness(qtbot, SpectrumProfile.OVERVIEW)

    overview.host.apply_display_options(SpectrumDisplayOptions(show_component_profiles=True))

    assert overview.host.display_command.show_component_profiles is False
    assert overview.widget.component_curves == []


def test_markers_are_uncoloured_while_component_curves_are_hidden(region_detail: _Harness) -> None:
    """Markers keep the default colour when no component curve identifies them."""
    region_detail.host.update_absorption_line_markers(region_detail.project)

    assert [marker.color for marker in region_detail.widget.markers] == [None, None]


def test_markers_take_the_colour_of_their_component_curve(region_detail: _Harness) -> None:
    """Each marker adopts the identity colour of its own component curve."""
    region_detail.host.apply_display_options(SpectrumDisplayOptions(show_component_profiles=True))

    assert [marker.color for marker in region_detail.widget.markers] == [
        component_curve_color(0),
        component_curve_color(1),
    ]


def test_disabled_components_neither_take_nor_consume_a_colour(region_detail: _Harness) -> None:
    """Colour order follows the enabled absorbers that own a component curve."""
    region_detail.project.model.components[0].enabled = False

    region_detail.host.apply_display_options(SpectrumDisplayOptions(show_component_profiles=True))

    assert [marker.color for marker in region_detail.widget.markers] == [
        None,
        component_curve_color(0),
    ]


def test_spectrum_view_forwards_display_options_to_the_plot_host(qtbot) -> None:
    """The view is the entry point the shell uses to change display toggles."""
    view = SpectrumView(plot_host_factory=create_default_spectrum_plot_host_factory())
    qtbot.addWidget(view)
    options = SpectrumDisplayOptions(show_error_spectrum=False, show_component_profiles=True)

    view.apply_display_options(options)

    assert view.display_options == options
    assert view.plot_host.display_command.show_error_spectrum is False


def test_spectrum_view_reports_whether_the_policy_supports_model_display(qtbot) -> None:
    """Applying a policy announces whether component curves can be shown at all."""
    view = SpectrumView(plot_host_factory=create_default_spectrum_plot_host_factory())
    qtbot.addWidget(view)
    announced: list[bool] = []
    view.model_display_supported_changed.connect(announced.append)

    view.apply_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL))
    view.apply_policy(analysis_spectrum_policy(SpectrumProfile.OVERVIEW))

    assert announced == [True, False]
