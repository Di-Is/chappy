"""Immutable selection helpers for velocity slices."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.presentation.velocity.view_model import VelocitySliceInfo


def resolve_velocity_slice_selection(slice_info: VelocitySliceInfo) -> bool:
    """Return the effective selection state for a slice."""
    return slice_info.selected if slice_info.selected is not None else slice_info.default_selected


def normalize_velocity_slices(
    slices: tuple[VelocitySliceInfo, ...] | list[VelocitySliceInfo],
) -> tuple[VelocitySliceInfo, ...]:
    """Return slices with default selection applied immutably."""
    return tuple(
        replace(slice_info, selected=resolve_velocity_slice_selection(slice_info))
        for slice_info in slices
    )


def preserve_velocity_slice_selection(
    previous_slices: tuple[VelocitySliceInfo, ...],
    incoming_slices: tuple[VelocitySliceInfo, ...] | list[VelocitySliceInfo],
) -> tuple[VelocitySliceInfo, ...]:
    """Return incoming slices while preserving known user selection state.

    Existing selection state wins for slices that can be matched to a previous
    slice identity. New slices still receive default selection through
    ``normalize_velocity_slices()``.
    """
    normalized_slices = normalize_velocity_slices(incoming_slices)
    previous_selection_by_key = {
        _slice_identity(slice_info): resolve_velocity_slice_selection(slice_info)
        for slice_info in previous_slices
    }
    return tuple(
        replace(
            slice_info,
            selected=previous_selection_by_key.get(
                _slice_identity(slice_info), slice_info.selected
            ),
        )
        for slice_info in normalized_slices
    )


def toggle_velocity_slice_selection(
    slices: tuple[VelocitySliceInfo, ...], *, absolute_index: int, checked: bool
) -> tuple[VelocitySliceInfo, ...]:
    """Return new slices after toggling one slice and matching tie-group siblings."""
    if absolute_index < 0 or absolute_index >= len(slices):
        return slices

    target = slices[absolute_index]
    tie_group_key = target.tie_group_key
    updated: list[VelocitySliceInfo] = []
    for index, slice_info in enumerate(slices):
        should_toggle = index == absolute_index
        if tie_group_key and slice_info.tie_group_key == tie_group_key:
            should_toggle = True
        if should_toggle and slice_info.selected != checked:
            updated.append(replace(slice_info, selected=checked))
        else:
            updated.append(slice_info)
    return tuple(updated)


def selected_velocity_slices(
    slices: tuple[VelocitySliceInfo, ...],
) -> tuple[VelocitySliceInfo, ...]:
    """Return selected slices in display order."""
    return tuple(slice_info for slice_info in slices if slice_info.selected)


def _slice_identity(slice_info: VelocitySliceInfo) -> tuple[str, str, float, str, str]:
    """Return a stable identity tuple for preserving slice-local UI state."""
    return (
        slice_info.line_id or "",
        slice_info.region_id or "",
        slice_info.rest_wavelength,
        slice_info.label,
        slice_info.tie_group_key,
    )
