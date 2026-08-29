"""Tests for shell velocity overlay DTO adapters."""

from __future__ import annotations

from chappy.gui.modes.analysis.region_detail import (
    OptimizeVelocityComponentContext,
    OptimizeVelocityOverlayContext,
    OptimizeVelocitySliceContext,
)
from chappy.gui.shell.velocity_overlay_adapter import (
    identify_velocity_overlay_info,
    optimize_velocity_overlay_info,
)
from chappy.presentation.identify import (
    IdentifyVelocityPlotContext,
    IdentifyVelocitySliceDescriptor,
)
from chappy.presentation.velocity import VelocityDisplayScopeKey


def test_identify_velocity_overlay_info_maps_slice_selection_defaults() -> None:
    """Identify velocity context should become shared spectrum overlay DTO."""
    context = IdentifyVelocityPlotContext(
        center_z=1.2,
        rest_wavelength=1548.2,
        observed_wavelength=3406.04,
        species_label="C IV 1548",
        new_candidate_analysis_half_width_kms=120.0,
        slices=(
            IdentifyVelocitySliceDescriptor(
                rest_wavelength=1548.2,
                label="C IV 1548",
                line_id="civ-1548",
                is_primary=True,
                default_selected=True,
                tie_group_key="preset:identify:group",
            ),
        ),
    )

    overlay = identify_velocity_overlay_info(context)

    assert overlay.center_z == 1.2
    assert overlay.new_candidate_analysis_half_width_kms == 120.0
    assert overlay.analysis_half_widths_kms == (120.0,)
    assert overlay.display_range_scope_key is not None
    assert overlay.selection_scope_key is not None
    assert len(overlay.slices) == 1
    slice_info = overlay.slices[0]
    assert slice_info.line_id == "civ-1548"
    assert slice_info.center_z == 1.2
    assert slice_info.is_primary is True
    assert slice_info.selected is None
    assert slice_info.default_selected is True
    assert slice_info.tie_group_key == "preset:identify:group"
    assert slice_info.analysis_half_width_kms == 120.0


def test_optimize_velocity_overlay_info_maps_components() -> None:
    """Optimize velocity context should preserve component marker metadata."""
    context = OptimizeVelocityOverlayContext(
        region_id="region-1",
        center_z=0.5,
        rest_wavelength=2796.35,
        observed_wavelength=4194.525,
        species_label="Mg II",
        slices=(
            OptimizeVelocitySliceContext(
                rest_wavelength=2796.35,
                label="Mg II 2796",
                center_z=0.5,
                line_id="line-1",
                region_id="region-1",
                analysis_half_width_kms=180.0,
                components=(
                    OptimizeVelocityComponentContext(
                        component_id="comp-1",
                        velocity=-12.0,
                        rest_wavelength=2796.35,
                        label="component",
                    ),
                ),
            ),
        ),
    )

    overlay = optimize_velocity_overlay_info(context)

    assert overlay.center_z == 0.5
    assert overlay.new_candidate_analysis_half_width_kms is None
    assert overlay.display_range_scope_key == VelocityDisplayScopeKey("optimize:region-1")
    assert overlay.analysis_half_widths_kms == (180.0,)
    assert overlay.selection_scope_key is not None
    assert len(overlay.slices) == 1
    slice_info = overlay.slices[0]
    assert slice_info.region_id == "region-1"
    assert slice_info.selected is None
    assert slice_info.analysis_half_width_kms == 180.0
    assert len(slice_info.components) == 1
    assert slice_info.components[0].component_id == "comp-1"
    assert slice_info.components[0].velocity == -12.0
