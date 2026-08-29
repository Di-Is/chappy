"""Adapters from identify velocity contexts to the shared spectrum overlay DTO."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.velocity import (
    VelocityDisplayScopeKey,
    VelocityOverlayInfo,
    VelocitySliceInfo,
)

if TYPE_CHECKING:
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
