"""Adapters from mode-local velocity contexts to shared spectrum overlay DTOs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.velocity import (
    VelocityComponentInfo,
    VelocityDisplayScopeKey,
    VelocityOverlayInfo,
    VelocitySliceInfo,
)

if TYPE_CHECKING:
    from chappy.gui.modes.analysis.region_detail import OptimizeVelocityOverlayContext
    from chappy.presentation.identify import IdentifyVelocityPlotContext


def identify_velocity_overlay_info(context: IdentifyVelocityPlotContext) -> VelocityOverlayInfo:
    """Convert identify velocity context into the shared spectrum DTO."""
    line_ids = ",".join(slice_info.line_id or "" for slice_info in context.slices)
    scope_key = (
        "identify:"
        f"{context.center_z:.12g}:"
        f"{context.rest_wavelength:.12g}:"
        f"{context.observed_wavelength:.12g}:"
        f"{line_ids}"
    )
    return VelocityOverlayInfo(
        selection_scope_key=scope_key,
        display_range_scope_key=VelocityDisplayScopeKey(scope_key),
        center_z=context.center_z,
        rest_wavelength=context.rest_wavelength,
        new_candidate_analysis_half_width_kms=context.new_candidate_analysis_half_width_kms,
        analysis_half_widths_kms=(context.new_candidate_analysis_half_width_kms,),
        slices=[
            VelocitySliceInfo(
                rest_wavelength=slice_info.rest_wavelength,
                label=slice_info.label,
                center_z=context.center_z,
                line_id=slice_info.line_id,
                is_primary=slice_info.is_primary,
                default_selected=slice_info.default_selected,
                tie_group_key=slice_info.tie_group_key,
                analysis_half_width_kms=context.new_candidate_analysis_half_width_kms,
            )
            for slice_info in context.slices
        ],
    )


def optimize_velocity_overlay_info(context: OptimizeVelocityOverlayContext) -> VelocityOverlayInfo:
    """Convert optimize velocity context into the shared spectrum DTO."""
    line_ids = ",".join(slice_context.line_id for slice_context in context.slices)
    region_ids = ",".join(slice_context.region_id or "" for slice_context in context.slices)
    return VelocityOverlayInfo(
        selection_scope_key=(
            "optimize:"
            f"{context.center_z:.12g}:"
            f"{context.rest_wavelength:.12g}:"
            f"{region_ids}:"
            f"{line_ids}"
        ),
        display_range_scope_key=VelocityDisplayScopeKey(f"optimize:{context.region_id}"),
        center_z=context.center_z,
        rest_wavelength=context.rest_wavelength,
        analysis_half_widths_kms=tuple(
            slice_context.analysis_half_width_kms for slice_context in context.slices
        ),
        slices=[
            VelocitySliceInfo(
                rest_wavelength=slice_context.rest_wavelength,
                label=slice_context.label,
                center_z=slice_context.center_z,
                line_id=slice_context.line_id,
                region_id=slice_context.region_id,
                is_primary=False,
                default_selected=False,
                tie_group_key=slice_context.tie_group_key,
                analysis_half_width_kms=slice_context.analysis_half_width_kms,
                components=[
                    VelocityComponentInfo(
                        component_id=component_context.component_id,
                        velocity=component_context.velocity,
                        rest_wavelength=component_context.rest_wavelength,
                        label=component_context.label,
                    )
                    for component_context in slice_context.components
                ],
            )
            for slice_context in context.slices
        ],
    )
