"""Unit tests for velocity slice render input construction."""

from __future__ import annotations

import numpy as np

from chappy.presentation.velocity import (
    VelocityCenterLineInfo,
    VelocityComponentInfo,
    VelocityComponentProfile,
    VelocityCurveSources,
    VelocityDisplayHalfWidth,
    VelocityMaskRegionInfo,
    VelocitySliceInfo,
    VelocitySpectrumData,
    build_velocity_slot_render_input,
    build_velocity_slice_render_input,
)


def _observed_spectrum() -> VelocitySpectrumData:
    """Return a small observed spectrum around the line center."""
    return VelocitySpectrumData(
        wavelength=np.array([1215.0, 1215.67, 1216.3], dtype=np.float64),
        flux=np.array([1.0, 0.8, 1.0], dtype=np.float64),
        error=np.array([0.05, 0.05, 0.05], dtype=np.float64),
    )


def _model_spectrum() -> VelocitySpectrumData:
    """Return a small model spectrum around the line center."""
    return VelocitySpectrumData(
        wavelength=np.array([1215.0, 1215.67, 1216.3], dtype=np.float64),
        flux=np.array([1.0, 0.9, 1.0], dtype=np.float64),
        error=None,
    )


def test_builder_returns_failure_without_observed_spectrum() -> None:
    """Missing observed data should become a typed failure state."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67, label="Lyα", tie_group_key="", center_z=0.0
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=None, model=None),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "failure"
    assert render_input.reason == "no_spectrum"
    assert render_input.selection_enabled is False


def test_slot_builder_returns_no_slices_state_for_empty_slot() -> None:
    """Missing slice metadata should become a typed no-slices state."""
    render_input = build_velocity_slot_render_input(
        None,
        default_title="Slot 1",
        sources=VelocityCurveSources(observed=_observed_spectrum(), model=None),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
        empty_reason="no_slices",
    )

    assert render_input.kind == "failure"
    assert render_input.reason == "no_slices"
    assert render_input.title == "Slot 1"
    assert render_input.selection_enabled is False


def test_builder_returns_failure_without_center_redshift() -> None:
    """Slice metadata without center redshift should become no-lines state."""
    slice_info = VelocitySliceInfo(rest_wavelength=1215.67, label="Lyα", tie_group_key="")

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum(), model=None),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "failure"
    assert render_input.reason == "no_lines"
    assert render_input.selection_enabled is True


def test_builder_returns_failure_when_window_has_no_samples() -> None:
    """An empty clipped slice should become a no-samples state."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=1300.0, label="Lyα", tie_group_key="", center_z=0.0
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum(), model=None),
        display_half_width=VelocityDisplayHalfWidth(10.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "failure"
    assert render_input.reason == "no_samples"


def test_builder_returns_failure_on_conversion_error() -> None:
    """Invalid slice parameters should become a conversion-failed state."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=0.0, label="Lyα", tie_group_key="", center_z=0.0
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum(), model=None),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "failure"
    assert render_input.reason == "conversion_failed"


def test_builder_returns_render_data_with_residual_and_overlays_in_optimize_mode() -> None:
    """Optimize mode should include model, residual, and overlay DTOs."""
    component = VelocityComponentInfo(
        component_id="comp_1", velocity=0.0, rest_wavelength=1215.67, label="c1"
    )
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Lyα",
        tie_group_key="",
        center_z=0.0,
        selected=True,
        analysis_half_width_kms=250.0,
        components=[component],
        mask_regions=[VelocityMaskRegionInfo(-25.0, 25.0, "gray")],
        center_lines=[VelocityCenterLineInfo(0.0, "yellow", "Lyα")],
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum(), model=_model_spectrum()),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=True,
    )

    assert render_input.kind == "data"
    assert render_input.selected is True
    assert render_input.model_velocity is not None
    assert render_input.model_flux is not None
    assert render_input.residual is not None
    assert render_input.mask_regions == tuple(slice_info.mask_regions)
    assert render_input.center_lines == tuple(slice_info.center_lines)
    assert render_input.component_markers == (component,)
    assert render_input.display_half_width_kms == 500.0
    assert render_input.analysis_bounds is not None
    assert render_input.analysis_bounds.lower_kms == -250.0
    assert render_input.analysis_bounds.upper_kms == 250.0
    assert render_input.analysis_out_of_view is False
    assert len(render_input.observed_velocity) == 3


def test_optimize_analysis_bounds_do_not_control_extraction_or_display_range() -> None:
    """A wider analysis range should be reported without changing display extraction."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Lyα",
        tie_group_key="",
        center_z=0.0,
        analysis_half_width_kms=350.0,
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum(), model=None),
        display_half_width=VelocityDisplayHalfWidth(200.0),
        unit="km/s",
        optimize_mode=True,
    )

    assert render_input.kind == "data"
    assert render_input.display_half_width_kms == 200.0
    assert render_input.analysis_bounds is not None
    assert render_input.analysis_bounds.half_width_kms == 350.0
    assert render_input.analysis_out_of_view is True
    assert min(render_input.observed_velocity) >= -200.0
    assert max(render_input.observed_velocity) <= 200.0


def test_builder_omits_optimize_only_outputs_in_identify_mode() -> None:
    """Identify mode should not include residual or overlay DTOs."""
    component = VelocityComponentInfo(
        component_id="comp_1", velocity=0.0, rest_wavelength=1215.67, label="c1"
    )
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Lyα",
        tie_group_key="",
        center_z=0.0,
        components=[component],
        mask_regions=[VelocityMaskRegionInfo(-25.0, 25.0, "gray")],
        center_lines=[VelocityCenterLineInfo(0.0, "yellow", "Lyα")],
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum(), model=_model_spectrum()),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "data"
    assert render_input.residual is None
    assert render_input.mask_regions == ()
    assert render_input.center_lines == ()
    assert render_input.component_markers == ()


def _component_profile(
    component_id: str, color: str, *, emphasized: bool = False
) -> VelocityComponentProfile:
    """Return one absorber transmission curve on the observed grid."""
    return VelocityComponentProfile(
        component_id=component_id,
        color=color,
        emphasized=emphasized,
        spectrum=VelocitySpectrumData(
            wavelength=np.array([1215.0, 1215.67, 1216.3], dtype=np.float64),
            flux=np.array([1.0, 0.85, 1.0], dtype=np.float64),
            error=None,
        ),
    )


def test_builder_drops_the_error_curve_when_the_user_hides_it() -> None:
    """Hiding the error spectrum removes it from the subplot data, not from the source."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67, label="Lyα", tie_group_key="", center_z=0.0
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum(), show_error_spectrum=False),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "data"
    assert render_input.observed_error is None


def test_builder_converts_component_profiles_into_velocity_curves() -> None:
    """Each component curve is sliced into the subplot's own velocity space."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67, label="Lyα", tie_group_key="", center_z=0.0
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(
            observed=_observed_spectrum(),
            component_profiles=(
                _component_profile("abs-1", "#1B9E77"),
                _component_profile("abs-2", "#D95F02", emphasized=True),
            ),
        ),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "data"
    curves = render_input.component_profile_curves
    assert [curve.component_id for curve in curves] == ["abs-1", "abs-2"]
    assert [curve.color for curve in curves] == ["#1B9E77", "#D95F02"]
    assert [curve.emphasized for curve in curves] == [False, True]
    for curve in curves:
        assert curve.velocity == render_input.observed_velocity
        assert len(curve.flux) == len(curve.velocity)


def test_builder_has_no_component_curves_when_none_are_supplied() -> None:
    """The default refresh carries no component curves."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67, label="Lyα", tie_group_key="", center_z=0.0
    )

    render_input = build_velocity_slice_render_input(
        slice_info,
        sources=VelocityCurveSources(observed=_observed_spectrum()),
        display_half_width=VelocityDisplayHalfWidth(500.0),
        unit="km/s",
        optimize_mode=False,
    )

    assert render_input.kind == "data"
    assert render_input.component_profile_curves == ()
