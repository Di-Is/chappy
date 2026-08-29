"""Tests for plot-local velocity display-range state."""

from __future__ import annotations

import pytest

from chappy.presentation.velocity import (
    VelocityDisplayHalfWidth,
    VelocityDisplayScopeKey,
    clear,
    commit_manual,
    derive_velocity_display_half_width,
    fit_view_to_analysis_ranges,
    initialize,
    switch_scope,
)


@pytest.mark.parametrize(
    ("analysis_half_widths", "expected"),
    [((230.0,), 250.0), ((100.0, 2000.0, 500.0), 2250.0), ((10.0,), 20.0)],
)
def test_derive_display_half_width_uses_next_nice_quantum(
    analysis_half_widths: tuple[float, ...], expected: float
) -> None:
    """The initial view should advance to the next deterministic quantum."""
    assert derive_velocity_display_half_width(analysis_half_widths).value == expected


@pytest.mark.parametrize("value", [9.99, 5000.01, float("nan"), float("inf")])
def test_display_half_width_rejects_invalid_values_without_clamping(value: float) -> None:
    """The presentation value object should never clamp invalid endpoints."""
    with pytest.raises(ValueError):
        VelocityDisplayHalfWidth(value)


def test_manual_state_survives_region_switch_and_explicit_fit_returns_to_auto() -> None:
    """Only the explicit fit action should replace a manual display range."""
    region_a = VelocityDisplayScopeKey("region-a")
    region_b = VelocityDisplayScopeKey("region-b")
    state = initialize(region_a, (230.0, 180.0))
    state = commit_manual(state, VelocityDisplayHalfWidth(600.0))

    switched = switch_scope(state, region_b, (1000.0,))

    assert switched.scope_key == "region-b"
    assert switched.source == "manual"
    assert switched.value.value == 600.0

    fitted = fit_view_to_analysis_ranges(region_b, (1000.0,))
    assert fitted.source == "auto"
    assert fitted.value.value == 1250.0
    assert clear() is None


def test_auto_state_rederives_only_when_region_changes() -> None:
    """Same-region refresh should preserve auto state despite changed analysis values."""
    region_a = VelocityDisplayScopeKey("region-a")
    region_b = VelocityDisplayScopeKey("region-b")
    state = initialize(region_a, (230.0,))

    refreshed = switch_scope(state, region_a, (1000.0,))
    switched = switch_scope(state, region_b, (1000.0,))

    assert refreshed is state
    assert refreshed.value.value == 250.0
    assert switched.value.value == 1250.0
