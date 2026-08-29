"""Unit tests for immutable velocity selection helpers."""

from __future__ import annotations

from chappy.presentation.velocity import (
    VelocitySliceInfo,
    normalize_velocity_slices,
    preserve_velocity_slice_selection,
    resolve_velocity_slice_selection,
    selected_velocity_slices,
    toggle_velocity_slice_selection,
)


def test_normalize_velocity_slices_applies_default_selection() -> None:
    """Default selection should be copied into selected state."""
    slices = (
        VelocitySliceInfo(
            rest_wavelength=2803.0, label="A", tie_group_key="", default_selected=True
        ),
        VelocitySliceInfo(
            rest_wavelength=2796.0, label="B", tie_group_key="", default_selected=False
        ),
    )

    normalized = normalize_velocity_slices(slices)

    assert [slice_info.selected for slice_info in normalized] == [True, False]
    assert [slice_info.selected for slice_info in slices] == [None, None]


def test_resolve_velocity_slice_selection_preserves_explicit_false() -> None:
    """Explicit deselection should not fall back to default selection."""
    slice_info = VelocitySliceInfo(
        rest_wavelength=2803.0, label="A", tie_group_key="", default_selected=True, selected=False
    )

    assert resolve_velocity_slice_selection(slice_info) is False


def test_toggle_velocity_slice_selection_syncs_declared_tie_group_members() -> None:
    """Toggling one slice should update all members of the same declared group."""
    slices = normalize_velocity_slices(
        (
            VelocitySliceInfo(rest_wavelength=2803.0, label="A", tie_group_key="preset:p:g"),
            VelocitySliceInfo(rest_wavelength=2796.0, label="B", tie_group_key="preset:p:g"),
            VelocitySliceInfo(rest_wavelength=2600.0, label="C", tie_group_key=""),
        )
    )

    updated = toggle_velocity_slice_selection(slices, absolute_index=0, checked=True)

    assert [slice_info.selected for slice_info in updated] == [True, True, False]
    assert [slice_info.selected for slice_info in slices] == [False, False, False]


def test_preserve_velocity_slice_selection_keeps_explicit_deselection() -> None:
    """Refresh should not reapply default selection after explicit deselection."""
    previous = (
        VelocitySliceInfo(
            rest_wavelength=2803.0,
            label="A",
            tie_group_key="",
            line_id="line-a",
            default_selected=True,
            selected=False,
        ),
    )
    incoming = (
        VelocitySliceInfo(
            rest_wavelength=2803.0,
            label="A",
            tie_group_key="",
            line_id="line-a",
            default_selected=True,
            selected=True,
        ),
    )

    preserved = preserve_velocity_slice_selection(previous, incoming)

    assert [slice_info.selected for slice_info in preserved] == [False]


def test_selected_velocity_slices_returns_selected_items_in_order() -> None:
    """Selected slice extraction should preserve display order."""
    slices = (
        VelocitySliceInfo(rest_wavelength=1.0, label="A", tie_group_key="", selected=True),
        VelocitySliceInfo(rest_wavelength=2.0, label="B", tie_group_key="", selected=False),
        VelocitySliceInfo(rest_wavelength=3.0, label="C", tie_group_key="", selected=True),
    )

    selected = selected_velocity_slices(slices)

    assert [slice_info.label for slice_info in selected] == ["A", "C"]
