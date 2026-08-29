"""Unit tests for velocity plot presentation helpers."""

from __future__ import annotations

from chappy.presentation.velocity import (
    VelocityGridPresenter,
    VelocitySliceInfo,
    build_velocity_pagination_state,
    build_visible_slice_states,
    compute_auto_flux_range,
)


def test_build_velocity_pagination_state_exposes_navigation_flags() -> None:
    """Pagination snapshot should expose next/previous availability."""
    page = VelocityGridPresenter().build_page(slice_count=8, subplot_count=6, requested_page=1)

    state = build_velocity_pagination_state(page)

    assert state.current_page == 1
    assert state.one_based_page == 2
    assert state.total_pages == 2
    assert state.can_go_previous is True
    assert state.can_go_next is False


def test_build_visible_slice_states_returns_titles_for_visible_slots() -> None:
    """Visible slot states should include slice titles and empty slot titles."""
    slices = (
        VelocitySliceInfo(rest_wavelength=1.0, label="Line 1", tie_group_key=""),
        VelocitySliceInfo(rest_wavelength=2.0, label="Line 2", tie_group_key="", selected=True),
    )
    page = VelocityGridPresenter().build_page(slice_count=2, subplot_count=3, requested_page=0)

    states = build_visible_slice_states(
        slices=slices, page=page, slot_label_builder=lambda number: f"Slot {number}"
    )

    assert [state.title for state in states] == ["Line 1", "Line 2", "Slot 3"]
    assert [state.absolute_index for state in states] == [0, 1, None]
    assert [state.selected for state in states] == [False, True, False]


def test_compute_auto_flux_range_returns_none_without_observed_ranges() -> None:
    """No observed ranges should produce no auto range."""
    assert compute_auto_flux_range((None, None)) is None


def test_compute_auto_flux_range_applies_expected_margin() -> None:
    """Auto Y range should include the configured margins."""
    auto_range = compute_auto_flux_range(((0.2, 0.8), (0.1, 0.9), None))

    assert auto_range == (-0.05, 1.05)
