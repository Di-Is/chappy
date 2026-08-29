"""Adapters from optimize velocity contexts to the shared spectrum overlay DTO."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.velocity import (
    VelocityComponentInfo,
    VelocityDisplayScopeKey,
    VelocityOverlayInfo,
    VelocitySliceInfo,
)

if TYPE_CHECKING:
    from chappy.gui.modes.analysis.region_detail.velocity_plot_controller import (
        OptimizeVelocityOverlayContext,
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
