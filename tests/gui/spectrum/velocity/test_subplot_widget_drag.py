"""Tests for VelocitySubplotWidget drag-related observable state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from chappy.gui.spectrum.velocity import VelocitySubplotWidget
from chappy.presentation.velocity import VelocityComponentInfo

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def velocity_subplot(qtbot: QtBot) -> VelocitySubplotWidget:
    """Create a VelocitySubplotWidget instance for testing."""
    subplot = VelocitySubplotWidget()
    qtbot.addWidget(subplot)
    return subplot


def test_set_components_exposes_component_ids_via_render_state(
    velocity_subplot: VelocitySubplotWidget,
) -> None:
    """set_components should update the observable component id snapshot."""
    velocity_subplot.set_components(
        [
            VelocityComponentInfo(
                component_id="abs_001", velocity=0.0, rest_wavelength=1215.67, label="Component 1"
            ),
            VelocityComponentInfo(
                component_id="abs_002", velocity=50.0, rest_wavelength=1215.67, label="Component 2"
            ),
        ]
    )

    assert velocity_subplot.render_state().component_ids == ("abs_001", "abs_002")


def test_get_component_at_velocity_prefers_closest_match(
    velocity_subplot: VelocitySubplotWidget,
) -> None:
    """get_component_at_velocity should return the closest in-range component."""
    velocity_subplot.set_components(
        [
            VelocityComponentInfo(
                component_id="closer", velocity=100.0, rest_wavelength=1215.67, label="Closer"
            ),
            VelocityComponentInfo(
                component_id="farther", velocity=150.0, rest_wavelength=1215.67, label="Farther"
            ),
        ]
    )

    result = velocity_subplot.get_component_at_velocity(120.0, tolerance=50.0)

    assert result is not None
    assert result.component_id == "closer"


def test_get_component_at_velocity_returns_none_without_match(
    velocity_subplot: VelocitySubplotWidget,
) -> None:
    """Out-of-range lookups should return no component."""
    velocity_subplot.set_components(
        [
            VelocityComponentInfo(
                component_id="far", velocity=100.0, rest_wavelength=1215.67, label="Far"
            )
        ]
    )

    assert velocity_subplot.get_component_at_velocity(300.0, tolerance=50.0) is None


def test_set_residual_marks_residual_visible(velocity_subplot: VelocitySubplotWidget) -> None:
    """Residual updates should be visible via render_state()."""
    velocity_subplot.set_residual(
        np.array([-100.0, 0.0, 100.0], dtype=np.float64),
        np.array([0.1, -0.05, 0.08], dtype=np.float64),
    )

    assert velocity_subplot.render_state().residual_visible is True


def test_set_data_clears_stale_residual_state(velocity_subplot: VelocitySubplotWidget) -> None:
    """Replacing observed data should clear older residual state."""
    velocity_subplot.set_residual(
        np.array([-100.0, 0.0, 100.0], dtype=np.float64),
        np.array([0.1, -0.05, 0.08], dtype=np.float64),
    )

    velocity_subplot.set_data(
        np.array([-100.0, 0.0, 100.0], dtype=np.float64),
        np.array([1.0, 0.8, 1.0], dtype=np.float64),
        np.array([0.1, 0.1, 0.1], dtype=np.float64),
        display_half_width_kms=200.0,
    )

    assert velocity_subplot.render_state().residual_visible is False
