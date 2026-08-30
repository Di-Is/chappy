"""Tests for region-scoped absorption markers and component curves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtWidgets import QWidget

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.analysis.contracts import SpectrumProfile
from chappy.gui.shell.analysis_surface_ui_adapter import analysis_spectrum_policy
from chappy.gui.spectrum.spectrum_plot import SpectrumPlotHost
from chappy.presentation.spectrum import (
    ModelWindowBuilder,
    SpectrumDisplayOptions,
    SpectrumRenderDTOAssembler,
    component_curve_color,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

    from chappy.presentation.spectrum import (
        AbsorptionMarkerInput,
        SpectrumComponentCurve,
        SpectrumPlotDisplayCommand,
    )


class _PlotWidget:
    """Plot surface double recording component curves and markers."""

    def __init__(self) -> None:
        """Initialize empty plot recordings."""
        self.display_commands: list[SpectrumPlotDisplayCommand] = []
        self.component_curves: list[tuple[SpectrumComponentCurve, ...]] = []
        self.markers: list[AbsorptionMarkerInput] = []

    def apply_display_command(self, command: SpectrumPlotDisplayCommand) -> None:
        """Record the applied display command."""
        self.display_commands.append(command)

    def set_component_profile_spectra(self, curves: tuple[SpectrumComponentCurve, ...]) -> None:
        """Record rendered component curves."""
        self.component_curves.append(curves)

    def clear_component_profiles(self) -> None:
        """Accept component curve clearing."""

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
    """Parent widget carrying the data bridge expected by the plot host."""

    def __init__(self, project: SpectroscopyProject) -> None:
        """Initialize a parent view for one project."""
        super().__init__()
        self.data_bridge = _DataBridge(project)


class _DataBridge:
    """Expose project state to the plot host."""

    def __init__(self, project: SpectroscopyProject) -> None:
        """Store the current project."""
        self.project = project


@dataclass(frozen=True)
class _Harness:
    """Plot host wired to a recording surface and two registered regions."""

    host: SpectrumPlotHost
    widget: _PlotWidget
    project: SpectroscopyProject
    first_region: AbsorptionRegion
    second_region: AbsorptionRegion


def _line(
    line_id: str, *, model_ids: list[str], lambda_range: tuple[float, float]
) -> AbsorptionLine:
    """Create an absorption line referencing model components."""
    return AbsorptionLine(
        line_id=line_id,
        species="C IV",
        rest_wavelength=1548.195,
        center_z=2.0,
        window_kms=500.0,
        multiplet_label="",
        transition_name=f"C IV {line_id}",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
        lambda_range=lambda_range,
        model_ids=model_ids,
    )


def _project() -> tuple[SpectroscopyProject, AbsorptionRegion, AbsorptionRegion]:
    """Create a project with an out-of-scope absorber between two scoped absorbers."""
    project = SpectroscopyProject(name="absorption-marker-scope")
    wavelength = np.linspace(4640.0, 4652.0, 240, dtype=np.float64)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength))
    )
    project.model.add_component(
        AbsorberComponent(
            name="first-region-a", component_id="region-a-1", wavelength=1548.195, redshift=2.0
        )
    )
    project.model.add_component(
        AbsorberComponent(
            name="second-region", component_id="region-b-1", wavelength=1549.0, redshift=2.0
        )
    )
    project.model.add_component(
        AbsorberComponent(
            name="first-region-b", component_id="region-a-2", wavelength=1550.0, redshift=2.0
        )
    )

    first_line = _line(
        "line-a", model_ids=["region-a-1", "region-a-2"], lambda_range=(4640.0, 4652.0)
    )
    second_line = _line("line-b", model_ids=["region-b-1"], lambda_range=(4640.0, 4652.0))
    project.absorption_lines[first_line.line_id] = first_line
    project.absorption_lines[second_line.line_id] = second_line
    first_region = AbsorptionRegion(region_id="region-a", line_ids=[first_line.line_id])
    second_region = AbsorptionRegion(region_id="region-b", line_ids=[second_line.line_id])
    project.absorption_regions[first_region.region_id] = first_region
    project.absorption_regions[second_region.region_id] = second_region
    return project, first_region, second_region


def _harness(qtbot: QtBot, profile: SpectrumProfile) -> _Harness:
    """Create a plot host focused on the first registered region."""
    project, first_region, second_region = _project()
    parent = _ParentView(project)
    qtbot.addWidget(parent)
    host = SpectrumPlotHost(parent, SpectrumRenderDTOAssembler(ModelWindowBuilder()))
    widget = _PlotWidget()
    host.plot_widget = widget
    host.set_project(project)
    host.set_selected_absorption_region(first_region)
    host.apply_policy(analysis_spectrum_policy(profile).plot_policy)
    return _Harness(
        host=host,
        widget=widget,
        project=project,
        first_region=first_region,
        second_region=second_region,
    )


def test_region_detail_markers_are_limited_to_selected_region(qtbot: QtBot) -> None:
    """Region detail omits markers belonging only to another region."""
    harness = _harness(qtbot, SpectrumProfile.REGION_DETAIL)

    assert [marker.component_id for marker in harness.widget.markers] == [
        "region-a-1",
        "region-a-2",
    ]


def test_overview_markers_include_all_regions(qtbot: QtBot) -> None:
    """Overview keeps the existing all-region marker behavior."""
    harness = _harness(qtbot, SpectrumProfile.OVERVIEW)

    assert [marker.component_id for marker in harness.widget.markers] == [
        "region-a-1",
        "region-b-1",
        "region-a-2",
    ]


def test_returning_to_overview_restores_all_region_markers(qtbot: QtBot) -> None:
    """Leaving Region Detail must restore the all-region marker scope."""
    harness = _harness(qtbot, SpectrumProfile.REGION_DETAIL)
    assert [marker.component_id for marker in harness.widget.markers] == [
        "region-a-1",
        "region-a-2",
    ]

    harness.host.apply_policy(analysis_spectrum_policy(SpectrumProfile.OVERVIEW).plot_policy)

    assert [marker.component_id for marker in harness.widget.markers] == [
        "region-a-1",
        "region-b-1",
        "region-a-2",
    ]


def test_changing_selected_region_rebuilds_marker_scope(qtbot: QtBot) -> None:
    """Selecting another region replaces the currently rendered markers."""
    harness = _harness(qtbot, SpectrumProfile.REGION_DETAIL)

    harness.host.set_selected_absorption_region(harness.second_region)

    assert [marker.component_id for marker in harness.widget.markers] == ["region-b-1"]


def test_scoped_marker_colors_keep_global_enabled_component_indices(qtbot: QtBot) -> None:
    """A filtered enabled absorber still consumes its shared curve color index."""
    harness = _harness(qtbot, SpectrumProfile.REGION_DETAIL)

    harness.host.apply_display_options(SpectrumDisplayOptions(show_component_profiles=True))

    curves = harness.widget.component_curves[-1]
    assert [curve.component_id for curve in curves] == ["region-a-1", "region-a-2"]
    assert [curve.color for curve in curves] == [
        component_curve_color(0),
        component_curve_color(2),
    ]
    assert [marker.color for marker in harness.widget.markers] == [
        component_curve_color(0),
        component_curve_color(2),
    ]
