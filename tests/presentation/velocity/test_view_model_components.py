"""Tests for velocity component view models and component assembly."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.presentation.spectrum import SpectrumDisplayOptions, component_curve_color
from chappy.presentation.velocity import (
    VelocityComponentInfo,
    VelocitySliceInfo,
    VelocityViewData,
    build_velocity_view_data,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def test_create_component_info() -> None:
    """VelocityComponentInfo should store component data."""
    info = VelocityComponentInfo(
        component_id="abs_001", velocity=50.0, rest_wavelength=1215.67, label="Lyα"
    )
    assert info.component_id == "abs_001"
    assert info.velocity == 50.0
    assert info.rest_wavelength == 1215.67
    assert info.label == "Lyα"


def test_component_info_handles_negative_velocity() -> None:
    """VelocityComponentInfo should preserve negative velocities."""
    info = VelocityComponentInfo(
        component_id="blue_001", velocity=-150.0, rest_wavelength=1215.67, label="Blueshifted"
    )
    assert info.velocity == -150.0


def test_slice_info_default_empty_components() -> None:
    """VelocitySliceInfo should default to an independent empty component list."""
    slice_info = VelocitySliceInfo(rest_wavelength=1215.67, label="Lyα", tie_group_key="")
    assert slice_info.components == []


def test_slice_info_components_are_independent() -> None:
    """Mutating one slice's components should not affect another slice."""
    slice_one = VelocitySliceInfo(rest_wavelength=1215.67, label="Slice 1", tie_group_key="")
    slice_two = VelocitySliceInfo(rest_wavelength=2796.35, label="Slice 2", tie_group_key="")

    slice_one.components.append(
        VelocityComponentInfo(
            component_id="test", velocity=0.0, rest_wavelength=1215.67, label="Test"
        )
    )

    assert len(slice_one.components) == 1
    assert len(slice_two.components) == 0


def test_velocity_slice_info_analysis_half_width_validation() -> None:
    """VelocitySliceInfo should validate optional scientific analysis half-widths."""
    assert (
        VelocitySliceInfo(
            rest_wavelength=1215.67, label="Lyα", tie_group_key=""
        ).analysis_half_width_kms
        is None
    )
    assert (
        VelocitySliceInfo(
            rest_wavelength=1215.67, label="Lyα", tie_group_key="", analysis_half_width_kms=500.0
        ).analysis_half_width_kms
        == 500.0
    )

    with pytest.raises(ValueError, match="finite and positive"):
        VelocitySliceInfo(
            rest_wavelength=1215.67, label="Lyα", tie_group_key="", analysis_half_width_kms=-300.0
        )
    with pytest.raises(ValueError, match="finite and positive"):
        VelocitySliceInfo(
            rest_wavelength=1215.67, label="Lyα", tie_group_key="", analysis_half_width_kms=0.0
        )


def test_velocity_slice_info_region_id_round_trip() -> None:
    """VelocitySliceInfo should preserve region identifiers."""
    assert (
        VelocitySliceInfo(rest_wavelength=2796.35, label="Mg II 2796", tie_group_key="").region_id
        is None
    )
    assert (
        VelocitySliceInfo(
            rest_wavelength=2796.35, label="Mg II 2796", tie_group_key="", region_id="region_1"
        ).region_id
        == "region_1"
    )


def test_build_velocity_view_data_builds_components_from_project() -> None:
    """Builder should derive VelocityComponentInfo entries from linked project components."""
    project, sample_component = _project_with_linked_component()
    slice_info = VelocitySliceInfo(
        rest_wavelength=1548.195,
        label="Test Slice",
        tie_group_key="",
        center_z=2.0,
        line_id="line_test_001",
    )

    components = _components_for_slice(project, slice_info)

    assert len(components) == 1
    assert components[0].component_id == sample_component.id
    assert abs(components[0].velocity) < 1


def test_build_velocity_view_data_updates_component_velocity_after_redshift_change() -> None:
    """Builder should reflect later component redshift edits in assembled velocity values."""
    project, sample_component = _project_with_linked_component()
    slice_info = VelocitySliceInfo(
        rest_wavelength=1548.195,
        label="Test Slice",
        tie_group_key="",
        center_z=2.0,
        line_id="line_test_001",
    )

    sample_component.parameters["redshift"].value = 2.001

    components = _components_for_slice(project, slice_info)

    assert len(components) == 1
    assert abs(components[0].velocity - 100.0) < 10.0


def test_build_velocity_view_data_handles_larger_component_drag_offsets() -> None:
    """Builder should keep components visible after a significant wavelength-side drag."""
    project, sample_component = _project_with_linked_component()
    slice_info = VelocitySliceInfo(
        rest_wavelength=1548.195,
        label="Test Slice",
        tie_group_key="",
        center_z=2.0,
        line_id="line_test_001",
    )

    sample_component.parameters["redshift"].value = 2.005

    components = _components_for_slice(project, slice_info)

    assert len(components) == 1
    assert abs(components[0].velocity - 500.0) < 50.0


def test_build_velocity_view_data_leaves_tie_label_unset_without_resolver() -> None:
    """Components should default to no tie label when no resolver is supplied."""
    project, _sample_component = _project_with_linked_component()
    slice_info = VelocitySliceInfo(
        rest_wavelength=1548.195,
        label="Test Slice",
        tie_group_key="",
        center_z=2.0,
        line_id="line_test_001",
    )

    components = _components_for_slice(project, slice_info)

    assert len(components) == 1
    assert components[0].tie_label is None


def test_build_velocity_view_data_applies_tie_label_resolver() -> None:
    """Components should carry the tie label returned by an injected resolver."""
    project, sample_component = _project_with_linked_component()
    slice_info = VelocitySliceInfo(
        rest_wavelength=1548.195,
        label="Test Slice",
        tie_group_key="",
        center_z=2.0,
        line_id="line_test_001",
    )

    components = _components_for_slice(
        project, slice_info, tie_label_resolver=lambda component: f"tie-{component.id}"
    )

    assert len(components) == 1
    assert components[0].tie_label == f"tie-{sample_component.id}"


def _components_for_slice(
    project: SpectroscopyProject,
    slice_info: VelocitySliceInfo,
    *,
    tie_label_resolver: Callable[[AbsorberComponent], str | None] | None = None,
) -> list[VelocityComponentInfo]:
    """Return builder-assembled components for one slice."""
    data = build_velocity_view_data(
        project,
        [slice_info],
        display_half_width_kms=500.0,
        include_optimize_overlays=False,
        tie_label_resolver=tie_label_resolver,
    )
    return list(data.slices[0].components)


def _project_with_linked_component() -> tuple[SpectroscopyProject, AbsorberComponent]:
    """Create a project with one line and one linked absorber component."""
    component = AbsorberComponent(
        name="Test Component", wavelength=1548.195, redshift=2.0, component_id="comp_test_001"
    )
    project = SpectroscopyProject()
    project.model.add_component(component)
    line = AbsorptionLine(
        line_id="line_test_001",
        species="C IV",
        rest_wavelength=1548.195,
        center_z=2.0,
        window_kms=500.0,
        model_ids=[component.id],
        multiplet_label="",
        transition_name="C IV 1548.2",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
    )
    project.absorption_lines[line.line_id] = line
    return project, component


def _project_with_absorbers() -> SpectroscopyProject:
    """Create a project with an observed spectrum and two enabled absorbers."""
    project = SpectroscopyProject()
    wavelength = np.linspace(4640.0, 4650.0, 200, dtype=np.float64)
    project.model.observed_spectrum = Spectrum(
        wavelength=wavelength, flux=np.ones_like(wavelength)
    )
    project.model.components.extend(
        [
            AbsorberComponent(component_id="abs-1", wavelength=1548.195, redshift=2.0),
            AbsorberComponent(component_id="abs-2", wavelength=1550.77, redshift=2.0),
        ]
    )
    return project


def _view_data(
    project: SpectroscopyProject,
    *,
    display_options: SpectrumDisplayOptions,
    emphasized_component_id: str | None = None,
) -> VelocityViewData:
    """Build velocity view data for a single Lyα slice."""
    return build_velocity_view_data(
        project,
        [
            VelocitySliceInfo(
                rest_wavelength=1548.195, label="C IV", tie_group_key="", center_z=2.0
            )
        ],
        display_half_width_kms=500.0,
        include_optimize_overlays=False,
        display_options=display_options,
        emphasized_component_id=emphasized_component_id,
    )


def test_velocity_view_data_omits_component_profiles_by_default() -> None:
    """Component curves are off unless the user turns them on."""
    data = _view_data(_project_with_absorbers(), display_options=SpectrumDisplayOptions())

    assert data.component_profiles == ()
    assert data.show_error_spectrum is True


def test_velocity_view_data_builds_one_component_profile_per_absorber() -> None:
    """Enabling component curves yields one coloured transmission curve per absorber."""
    project = _project_with_absorbers()

    data = _view_data(
        project,
        display_options=SpectrumDisplayOptions(show_component_profiles=True),
        emphasized_component_id="abs-2",
    )

    assert [model.component_id for model in data.component_profiles] == ["abs-1", "abs-2"]
    assert [model.color for model in data.component_profiles] == [
        component_curve_color(0),
        component_curve_color(1),
    ]
    assert [model.emphasized for model in data.component_profiles] == [False, True]
    assert project.model.observed_spectrum is not None
    for model in data.component_profiles:
        np.testing.assert_array_equal(
            model.spectrum.wavelength, project.model.observed_spectrum.wavelength
        )
        assert model.spectrum.error is None


def test_velocity_view_data_carries_the_error_spectrum_toggle() -> None:
    """The error toggle reaches the subplot builders through the view data."""
    data = _view_data(
        _project_with_absorbers(),
        display_options=SpectrumDisplayOptions(show_error_spectrum=False),
    )

    assert data.show_error_spectrum is False


def test_velocity_view_data_carries_the_error_toggle_without_a_project() -> None:
    """A project-less refresh still reports the user's error-curve choice."""
    data = build_velocity_view_data(
        None,
        [],
        display_half_width_kms=500.0,
        include_optimize_overlays=False,
        display_options=SpectrumDisplayOptions(show_error_spectrum=False),
    )

    assert data.show_error_spectrum is False
    assert data.component_profiles == ()


def _linked_slice_components(
    *, display_options: SpectrumDisplayOptions, emphasized_component_id: str | None
) -> list[VelocityComponentInfo]:
    """Return slice markers for a project whose line owns two coloured absorbers."""
    project = SpectroscopyProject()
    wavelength = np.linspace(4640.0, 4650.0, 200, dtype=np.float64)
    project.model.observed_spectrum = Spectrum(
        wavelength=wavelength, flux=np.ones_like(wavelength)
    )
    first = AbsorberComponent(component_id="abs-1", wavelength=1548.195, redshift=2.0)
    second = AbsorberComponent(component_id="abs-2", wavelength=1548.195, redshift=2.0)
    project.model.add_component(first)
    project.model.add_component(second)
    project.absorption_lines["line-1"] = AbsorptionLine(
        line_id="line-1",
        species="C IV",
        rest_wavelength=1548.195,
        center_z=2.0,
        window_kms=500.0,
        model_ids=[first.id, second.id],
        multiplet_label="",
        transition_name="C IV 1548.2",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
    )

    data = build_velocity_view_data(
        project,
        [
            VelocitySliceInfo(
                rest_wavelength=1548.195,
                label="C IV",
                tie_group_key="",
                center_z=2.0,
                line_id="line-1",
            )
        ],
        display_half_width_kms=500.0,
        include_optimize_overlays=True,
        display_options=display_options,
        emphasized_component_id=emphasized_component_id,
    )
    return list(data.slices[0].components)


def test_velocity_slice_markers_emphasise_the_selected_component() -> None:
    """The selected component's marker reads emphasised, like the wavelength plot's."""
    components = _linked_slice_components(
        display_options=SpectrumDisplayOptions(show_component_profiles=True),
        emphasized_component_id="abs-2",
    )

    assert [component.selected for component in components] == [False, True]


def test_velocity_slice_markers_share_the_component_curve_colours() -> None:
    """Marker colours match the profile curves so label and curve read as one component."""
    components = _linked_slice_components(
        display_options=SpectrumDisplayOptions(show_component_profiles=True),
        emphasized_component_id=None,
    )

    assert [component.color for component in components] == [
        component_curve_color(0),
        component_curve_color(1),
    ]


def test_velocity_slice_markers_stay_uncoloured_without_component_profiles() -> None:
    """With profiles off there is no curve to match, so markers keep the default colour."""
    components = _linked_slice_components(
        display_options=SpectrumDisplayOptions(), emphasized_component_id="abs-2"
    )

    assert [component.color for component in components] == [None, None]
    assert [component.selected for component in components] == [False, True]
