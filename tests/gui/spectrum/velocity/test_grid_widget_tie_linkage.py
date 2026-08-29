"""Tests for tie-set marker labels and live drag linkage in the velocity grid."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.spectrum.velocity import (
    VelocityGridWidget,
    VelocityPointerEvent,
    VelocitySubplotWidget,
)
from chappy.presentation.velocity import (
    VelocityComponentInfo,
    VelocitySliceInfo,
    build_velocity_view_data,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _project_with_dummy_spectrum() -> SpectroscopyProject:
    """Create a project carrying only an observed spectrum, no lines or components."""
    project = SpectroscopyProject()
    project.model.observed_spectrum = SimpleNamespace(
        wavelength=np.linspace(1000.0, 10000.0, 1000), flux=np.ones(1000), error=np.full(1000, 0.1)
    )
    return project


@pytest.fixture
def velocity_grid(qtbot: QtBot) -> VelocityGridWidget:
    """Create a VelocityGridWidget instance for testing."""
    view = VelocityGridWidget()
    qtbot.addWidget(view)
    return view


def test_optimize_mode_renders_tie_labelled_component_marker(
    velocity_grid: VelocityGridWidget,
) -> None:
    """A resolver-supplied tie label should surface as a rendered marker in optimize mode."""
    component = VelocityComponentInfo(
        component_id="comp_1", velocity=0.0, rest_wavelength=1215.67, label="c1", tie_label="A"
    )
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Lyα",
        tie_group_key="",
        center_z=2.0,
        components=[component],
        analysis_half_width_kms=150.0,
    )
    velocity_grid.set_mode("optimize")
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            _project_with_dummy_spectrum(),
            [slice_info],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=True,
        )
    )

    assert _subplots(velocity_grid)[0].render_state().component_marker_count == 1


def test_identify_mode_omits_component_markers(velocity_grid: VelocityGridWidget) -> None:
    """Identify mode should not render component markers, tied or otherwise."""
    component = VelocityComponentInfo(
        component_id="comp_1", velocity=0.0, rest_wavelength=1215.67, label="c1", tie_label="A"
    )
    slice_info = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Lyα",
        tie_group_key="",
        center_z=2.0,
        components=[component],
    )
    velocity_grid.set_mode("identify")
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            _project_with_dummy_spectrum(),
            [slice_info],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )

    assert _subplots(velocity_grid)[0].render_state().component_marker_count == 0


def test_dragging_shared_redshift_component_mirrors_overlay_to_tied_subplot(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Dragging one z-shared component should live-update overlays in other subplots."""
    shared_ids = frozenset({"shared_1", "shared_2"})
    velocity_grid.set_tie_member_resolver(
        lambda component_id: shared_ids if component_id in shared_ids else frozenset()
    )

    slice_a = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Slice A",
        tie_group_key="",
        center_z=1.0,
        components=[
            VelocityComponentInfo(
                component_id="shared_1", velocity=0.0, rest_wavelength=1215.67, label="c1"
            )
        ],
        analysis_half_width_kms=150.0,
    )
    slice_b = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Slice B",
        tie_group_key="",
        center_z=1.0,
        components=[
            VelocityComponentInfo(
                component_id="shared_2", velocity=0.0, rest_wavelength=1215.67, label="c2"
            )
        ],
    )
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            None,
            [slice_a, slice_b],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )

    subplot_a, subplot_b = _subplots(velocity_grid)[:2]
    assert subplot_b.has_drag_overlay() is False

    subplot_a.mouse_moved.emit(
        VelocityPointerEvent(velocity=50.0, flux=0.8, component=slice_a.components[0])
    )

    assert subplot_b.has_drag_overlay() is True


def test_unrelated_subplot_is_not_linked_during_drag(velocity_grid: VelocityGridWidget) -> None:
    """A subplot with no tied component should not receive a mirrored overlay."""
    shared_ids = frozenset({"shared_1", "shared_2"})
    velocity_grid.set_tie_member_resolver(
        lambda component_id: shared_ids if component_id in shared_ids else frozenset()
    )

    slice_a = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Slice A",
        tie_group_key="",
        center_z=1.0,
        components=[
            VelocityComponentInfo(
                component_id="shared_1", velocity=0.0, rest_wavelength=1215.67, label="c1"
            )
        ],
    )
    slice_c = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Slice C",
        tie_group_key="",
        center_z=1.0,
        components=[
            VelocityComponentInfo(
                component_id="unrelated", velocity=0.0, rest_wavelength=1215.67, label="c3"
            )
        ],
    )
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            None,
            [slice_a, slice_c],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )

    subplot_a, subplot_c = _subplots(velocity_grid)[:2]

    subplot_a.mouse_moved.emit(
        VelocityPointerEvent(velocity=50.0, flux=0.8, component=slice_a.components[0])
    )

    assert subplot_c.has_drag_overlay() is False


def test_drag_release_clears_linked_overlay(velocity_grid: VelocityGridWidget) -> None:
    """Completing a drag should clear the mirrored overlay in tied subplots."""
    shared_ids = frozenset({"shared_1", "shared_2"})
    velocity_grid.set_tie_member_resolver(
        lambda component_id: shared_ids if component_id in shared_ids else frozenset()
    )

    slice_a = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Slice A",
        tie_group_key="",
        center_z=1.0,
        components=[
            VelocityComponentInfo(
                component_id="shared_1", velocity=0.0, rest_wavelength=1215.67, label="c1"
            )
        ],
    )
    slice_b = VelocitySliceInfo(
        rest_wavelength=1215.67,
        label="Slice B",
        tie_group_key="",
        center_z=1.0,
        components=[
            VelocityComponentInfo(
                component_id="shared_2", velocity=0.0, rest_wavelength=1215.67, label="c2"
            )
        ],
    )
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            None,
            [slice_a, slice_b],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=False,
        )
    )

    subplot_a, subplot_b = _subplots(velocity_grid)[:2]
    subplot_a.mouse_moved.emit(
        VelocityPointerEvent(velocity=50.0, flux=0.8, component=slice_a.components[0])
    )
    assert subplot_b.has_drag_overlay() is True

    subplot_a.mouse_released.emit(
        VelocityPointerEvent(velocity=50.0, flux=0.8, component=slice_a.components[0])
    )

    assert subplot_b.has_drag_overlay() is False


def _subplots(view: VelocityGridWidget) -> tuple[VelocitySubplotWidget, ...]:
    """Return the subplot children in grid order."""
    return tuple(view.findChildren(VelocitySubplotWidget))
