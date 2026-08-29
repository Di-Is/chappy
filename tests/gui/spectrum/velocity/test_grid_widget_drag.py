"""Tests for VelocityGridWidget drag signal bridging."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from chappy.gui.spectrum.velocity import (
    VelocityGridWidget,
    VelocityPointerEvent,
    VelocitySubplotWidget,
)
from chappy.presentation.velocity import (
    VelocityComponentInfo,
    VelocityDragRequest,
    VelocitySliceInfo,
    build_velocity_view_data,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def velocity_grid(qtbot: QtBot) -> VelocityGridWidget:
    """Create a VelocityGridWidget instance for testing."""
    view = VelocityGridWidget()
    qtbot.addWidget(view)
    return view


def test_mouse_press_with_component_emits_drag_request(velocity_grid: VelocityGridWidget) -> None:
    """Subplot drag start should surface as a typed grid-level request."""
    requests: list[VelocityDragRequest] = []
    velocity_grid.sig_velocity_drag_requested.connect(requests.append)
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            None,
            [
                VelocitySliceInfo(
                    rest_wavelength=1215.67, label="Lyα", tie_group_key="", center_z=2.0
                )
            ],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )
    subplot = _subplots(velocity_grid)[0]

    subplot.mouse_pressed.emit(
        VelocityPointerEvent(
            velocity=125.0,
            flux=0.8,
            component=VelocityComponentInfo(
                component_id="comp_1", velocity=100.0, rest_wavelength=1215.67, label="Component 1"
            ),
        )
    )

    assert requests == [
        VelocityDragRequest(
            component_id="comp_1", velocity=125.0, rest_wavelength=1215.67, flux=0.8, center_z=2.0
        )
    ]


def test_mouse_press_without_component_does_not_emit_drag_request(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Subplot press without a draggable component should not start a drag."""
    requests: list[VelocityDragRequest] = []
    velocity_grid.sig_velocity_drag_requested.connect(requests.append)
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            None,
            [
                VelocitySliceInfo(
                    rest_wavelength=1215.67, label="Lyα", tie_group_key="", center_z=2.0
                )
            ],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )

    _subplots(velocity_grid)[0].mouse_pressed.emit(
        VelocityPointerEvent(velocity=125.0, flux=0.8, component=None)
    )

    assert requests == []


def _subplots(view: VelocityGridWidget) -> tuple[VelocitySubplotWidget, ...]:
    """Return the subplot children in grid order."""
    return tuple(view.findChildren(VelocitySubplotWidget))
