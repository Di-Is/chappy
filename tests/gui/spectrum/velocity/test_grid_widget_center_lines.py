"""Tests for VelocityGridWidget center-line rendering."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Literal

import numpy as np
import pytest

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.spectrum.velocity import VelocityGridWidget, VelocitySubplotWidget
from chappy.presentation.velocity import (
    VelocityDisplayHalfWidth,
    VelocitySliceInfo,
    build_velocity_view_data,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

_LIVE_SUBPLOTS: list[VelocitySubplotWidget] = []


@pytest.fixture
def velocity_grid(qtbot: QtBot) -> VelocityGridWidget:
    """Create a VelocityGridWidget instance for testing."""
    view = VelocityGridWidget()
    qtbot.addWidget(view)
    return view


@pytest.fixture
def project_with_mg2_region() -> SpectroscopyProject:
    """Create a SpectroscopyProject with an Mg II region but no linked components."""
    project = SpectroscopyProject()
    project.model.observed_spectrum = _dummy_spectrum()
    project.absorption_lines["mg2_2796"] = _make_line(
        "mg2_2796", rest_wavelength=2796.35, species="Mg II", region_id="region_1"
    )
    project.absorption_lines["mg2_2803"] = _make_line(
        "mg2_2803", rest_wavelength=2803.53, species="Mg II", region_id="region_1"
    )
    project.absorption_regions["region_1"] = AbsorptionRegion(
        region_id="region_1", line_ids=["mg2_2796", "mg2_2803"]
    )
    return project


@pytest.fixture
def project_with_mg2_components() -> SpectroscopyProject:
    """Create a SpectroscopyProject with an Mg II doublet and linked components."""
    project = SpectroscopyProject()
    project.model.observed_spectrum = _dummy_spectrum()
    comp_2796 = AbsorberComponent(
        name="Mg II 2796", wavelength=2796.35, redshift=1.5, component_id="comp_mg2_2796"
    )
    comp_2803 = AbsorberComponent(
        name="Mg II 2803", wavelength=2803.53, redshift=1.5, component_id="comp_mg2_2803"
    )
    project.model.components.extend([comp_2796, comp_2803])
    project.absorption_lines["mg2_2796"] = _make_line(
        "mg2_2796",
        rest_wavelength=2796.35,
        species="Mg II",
        region_id="region_1",
        model_ids=["comp_mg2_2796"],
    )
    project.absorption_lines["mg2_2803"] = _make_line(
        "mg2_2803",
        rest_wavelength=2803.53,
        species="Mg II",
        region_id="region_1",
        model_ids=["comp_mg2_2803"],
    )
    project.absorption_regions["region_1"] = AbsorptionRegion(
        region_id="region_1", line_ids=["mg2_2796", "mg2_2803"]
    )
    return project


def test_subplot_center_line_count_updates_without_private_access(qtbot: QtBot) -> None:
    """Subplot render state should expose center-line counts."""
    subplot = VelocitySubplotWidget()
    _LIVE_SUBPLOTS.append(subplot)
    qtbot.addWidget(subplot)

    assert subplot.render_state().center_line_count == 0

    subplot.add_center_line(0.0)
    subplot.add_center_line(100.0)
    assert subplot.render_state().center_line_count == 2

    subplot.clear_center_lines()
    assert subplot.render_state().center_line_count == 0


def test_center_line_rendering_replaces_existing_lines(
    velocity_grid: VelocityGridWidget, project_with_mg2_components: SpectroscopyProject
) -> None:
    """Rendering a slice should replace pre-existing center lines."""
    subplot = _first_subplot(velocity_grid)
    subplot.add_center_line(50.0)
    assert subplot.render_state().center_line_count == 1

    rendered = _display_slice(
        velocity_grid,
        VelocitySliceInfo(
            rest_wavelength=2796.35,
            label="Mg II 2796",
            tie_group_key="",
            center_z=1.5,
            line_id="mg2_2796",
            region_id="region_1",
        ),
        project=project_with_mg2_components,
    )

    assert rendered.render_state().center_line_count >= 1


def test_center_lines_are_absent_without_region_id(velocity_grid: VelocityGridWidget) -> None:
    """Missing region_id should suppress center-line rendering."""
    rendered = _display_slice(
        velocity_grid,
        VelocitySliceInfo(
            rest_wavelength=2796.35,
            label="Mg II 2796",
            tie_group_key="",
            center_z=1.5,
            region_id=None,
        ),
    )

    assert rendered.render_state().center_line_count == 0


def test_center_lines_are_absent_without_project(velocity_grid: VelocityGridWidget) -> None:
    """Missing project context should leave center lines absent."""
    rendered = _display_slice(
        velocity_grid,
        VelocitySliceInfo(
            rest_wavelength=2796.35,
            label="Mg II 2796",
            tie_group_key="",
            center_z=1.5,
            region_id="region_1",
        ),
    )

    assert rendered.render_state().center_line_count == 0


def test_center_lines_include_primary_and_multiplet_lines(
    velocity_grid: VelocityGridWidget, project_with_mg2_components: SpectroscopyProject
) -> None:
    """Wide velocity windows should render both the primary and paired multiplet lines."""
    rendered = _display_slice(
        velocity_grid,
        VelocitySliceInfo(
            rest_wavelength=2796.35,
            label="Mg II 2796",
            tie_group_key="",
            center_z=1.5,
            line_id="mg2_2796",
            region_id="region_1",
        ),
        velocity_window_kms=1000.0,
        project=project_with_mg2_components,
    )

    assert rendered.render_state().center_line_count == 2


def test_center_lines_skip_lines_outside_velocity_window(
    velocity_grid: VelocityGridWidget, project_with_mg2_components: SpectroscopyProject
) -> None:
    """Narrow velocity windows should omit paired lines outside the slice extent."""
    rendered = _display_slice(
        velocity_grid,
        VelocitySliceInfo(
            rest_wavelength=2796.35,
            label="Mg II 2796",
            tie_group_key="",
            center_z=1.5,
            line_id="mg2_2796",
            region_id="region_1",
        ),
        velocity_window_kms=200.0,
        project=project_with_mg2_components,
    )

    assert rendered.render_state().center_line_count == 1


def test_center_lines_are_absent_when_region_has_no_components(
    velocity_grid: VelocityGridWidget, project_with_mg2_region: SpectroscopyProject
) -> None:
    """Regions without linked components should not render center lines."""
    rendered = _display_slice(
        velocity_grid,
        VelocitySliceInfo(
            rest_wavelength=2796.35,
            label="Mg II 2796",
            tie_group_key="",
            center_z=1.5,
            line_id="mg2_2796",
            region_id="region_1",
        ),
        velocity_window_kms=1000.0,
        project=project_with_mg2_region,
    )

    assert rendered.render_state().center_line_count == 0


def test_identify_mode_clears_center_lines(
    velocity_grid: VelocityGridWidget, project_with_mg2_components: SpectroscopyProject
) -> None:
    """Switching from optimize to identify mode should clear rendered center lines."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=2796.35,
        label="Mg II 2796",
        tie_group_key="",
        center_z=1.5,
        line_id="mg2_2796",
        region_id="region_1",
    )
    rendered = _display_slice(
        velocity_grid, slice_info, context="optimize", project=project_with_mg2_components
    )
    assert rendered.render_state().center_line_count >= 1

    rendered = _display_slice(
        velocity_grid, slice_info, context="identify", project=project_with_mg2_components
    )

    assert rendered.render_state().center_line_count == 0


def test_empty_slice_render_clears_prior_center_lines(
    velocity_grid: VelocityGridWidget, project_with_mg2_components: SpectroscopyProject
) -> None:
    """Early-return placeholder rendering should still clear old center lines."""
    valid_slice = VelocitySliceInfo(
        rest_wavelength=2796.35,
        label="Mg II 2796",
        tie_group_key="",
        center_z=1.5,
        line_id="mg2_2796",
        region_id="region_1",
    )
    rendered = _display_slice(
        velocity_grid, valid_slice, context="optimize", project=project_with_mg2_components
    )
    assert rendered.render_state().center_line_count >= 1

    empty_slice = VelocitySliceInfo(
        rest_wavelength=1000.0,
        label="Invalid",
        tie_group_key="",
        center_z=1.5,
        line_id="invalid",
        region_id="region_1",
    )
    rendered = _display_slice(velocity_grid, empty_slice, context="identify")

    assert rendered.render_state().center_line_count == 0


def _display_slice(
    view: VelocityGridWidget,
    slice_info: VelocitySliceInfo,
    *,
    context: Literal["identify", "optimize"] = "optimize",
    velocity_window_kms: float = 1000.0,
    project: SpectroscopyProject | None = None,
) -> VelocitySubplotWidget:
    """Render a single slice through VelocityGridWidget's public update methods."""
    view.set_mode(context)
    view.set_display_half_width(VelocityDisplayHalfWidth(velocity_window_kms))
    if context == "optimize":
        slice_info.analysis_half_width_kms = 150.0
    view.apply_view_data(
        build_velocity_view_data(
            project,
            [slice_info],
            display_half_width_kms=velocity_window_kms,
            include_optimize_overlays=context == "optimize",
        )
    )
    return _first_subplot(view)


def _first_subplot(view: VelocityGridWidget) -> VelocitySubplotWidget:
    """Return the first subplot child from the grid."""
    return tuple(view.findChildren(VelocitySubplotWidget))[0]


def _make_line(
    line_id: str,
    *,
    rest_wavelength: float = 1215.67,
    species: str = "H I",
    center_z: float = 1.5,
    region_id: str | None = None,
    model_ids: list[str] | None = None,
) -> AbsorptionLine:
    """Create a minimal AbsorptionLine for testing."""
    return AbsorptionLine(
        line_id=line_id,
        species=species,
        rest_wavelength=rest_wavelength,
        center_z=center_z,
        window_kms=150.0,
        region_id=region_id,
        multiplet_ids=[],
        model_ids=model_ids or [],
        multiplet_label="",
        transition_name=f"{species} {rest_wavelength:.1f}",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )


def _dummy_spectrum() -> SimpleNamespace:
    """Create a dummy spectrum for testing."""
    return SimpleNamespace(
        wavelength=np.linspace(1000.0, 10000.0, 1000), flux=np.ones(1000), error=np.full(1000, 0.1)
    )
