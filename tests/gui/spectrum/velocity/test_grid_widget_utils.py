"""Tests for VelocityGridWidget pagination, selection, and residual state."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import numpy as np
import pytest

from chappy.gui.spectrum.velocity import VelocityGridWidget, VelocitySubplotWidget
from chappy.presentation.velocity import VelocitySliceInfo, build_velocity_view_data

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


@pytest.fixture
def velocity_grid(qtbot: QtBot) -> VelocityGridWidget:
    """Create a VelocityGridWidget instance for testing."""
    view = VelocityGridWidget()
    qtbot.addWidget(view)
    return view


def test_velocity_grid_syncs_declared_tie_group_selection(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Toggling one slice should mirror selection across declared group members."""
    _apply_slices(
        velocity_grid,
        [
            VelocitySliceInfo(
                rest_wavelength=2803.0,
                label="Mg II 2803",
                line_id="base",
                is_primary=True,
                tie_group_key="preset:test:group",
            ),
            VelocitySliceInfo(
                rest_wavelength=2796.0,
                label="Mg II 2796",
                line_id="comp",
                tie_group_key="preset:test:group",
            ),
            VelocitySliceInfo(
                rest_wavelength=2600.0, label="Fe II 2600", tie_group_key="", line_id="other"
            ),
        ],
    )
    subplots = _subplots(velocity_grid)

    for subplot in subplots:
        subplot.set_selection_enabled(True)
        subplot.set_checked(False)

    subplots[0].set_checked(True)
    subplots[0].selection_toggled.emit(True)

    assert [slice_info.selected for slice_info in velocity_grid.visible_slice_states()[:3]] == [
        True,
        True,
        False,
    ]
    assert subplots[0].is_checked() is True
    assert subplots[1].is_checked() is True

    subplots[1].set_checked(False)
    subplots[1].selection_toggled.emit(False)

    assert [slice_info.selected for slice_info in velocity_grid.visible_slice_states()[:3]] == [
        False,
        False,
        False,
    ]
    assert subplots[0].is_checked() is False


def test_velocity_grid_pagination_controls(velocity_grid: VelocityGridWidget) -> None:
    """Pagination state and visible slot titles should track the active page."""
    slices = [
        VelocitySliceInfo(
            rest_wavelength=5000.0 + index,
            label=f"Line {index}",
            tie_group_key="",
            center_z=2.0,
            line_id=f"line-{index}",
        )
        for index in range(8)
    ]
    _apply_slices(velocity_grid, slices)

    assert velocity_grid.pagination_state().current_page == 0
    assert _page_info(velocity_grid) == (1, 2)
    assert [state.title for state in velocity_grid.visible_slice_states()[:3]] == [
        "Line 0",
        "Line 1",
        "Line 2",
    ]

    velocity_grid._set_page(1)

    assert velocity_grid.pagination_state().current_page == 1
    assert _page_info(velocity_grid) == (2, 2)
    assert [state.title for state in velocity_grid.visible_slice_states()[:3]] == [
        "Line 6",
        "Line 7",
        "Slot 9",
    ]
    assert _subplots(velocity_grid)[0].render_state().selection_checked is False


@pytest.mark.parametrize(
    ("slice_count", "expected_cells"), [(0, 1), (1, 1), (2, 2), (3, 3), (5, 5), (6, 6)]
)
def test_velocity_grid_lays_out_only_populated_cells(
    velocity_grid: VelocityGridWidget, slice_count: int, expected_cells: int
) -> None:
    """Surplus subplot cells must leave the layout instead of rendering placeholders."""
    slices = [
        VelocitySliceInfo(
            rest_wavelength=5000.0 + index,
            label=f"Line {index}",
            tie_group_key="",
            line_id=f"line-{index}",
        )
        for index in range(slice_count)
    ]
    _apply_slices(velocity_grid, slices)

    subplots = _subplots(velocity_grid)
    assert [not subplot.isHidden() for subplot in subplots] == [
        index < expected_cells for index in range(len(subplots))
    ]


def test_velocity_grid_last_page_hides_unpopulated_cells(
    velocity_grid: VelocityGridWidget,
) -> None:
    """The final page's remainder must follow the same adaptive layout rule."""
    slices = [
        VelocitySliceInfo(
            rest_wavelength=5000.0 + index,
            label=f"Line {index}",
            tie_group_key="",
            line_id=f"line-{index}",
        )
        for index in range(8)
    ]
    _apply_slices(velocity_grid, slices)
    velocity_grid._set_page(1)

    subplots = _subplots(velocity_grid)
    assert [not subplot.isHidden() for subplot in subplots] == [
        True,
        True,
        False,
        False,
        False,
        False,
    ]


def test_velocity_grid_page_resets_when_slice_count_shrinks(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Shrinking the slice count should clamp the current page back into range."""
    slices = [
        VelocitySliceInfo(
            rest_wavelength=6000.0 + index,
            label=f"Line {index}",
            tie_group_key="",
            line_id=f"line-{index}",
        )
        for index in range(10)
    ]
    _apply_slices(velocity_grid, slices)
    velocity_grid._set_page(1)

    _apply_slices(velocity_grid, slices[:5])

    assert velocity_grid.pagination_state().current_page == 0
    assert _page_info(velocity_grid) == (1, 1)
    assert velocity_grid.visible_slice_states()[5].title == "Slot 6"


def test_velocity_grid_apply_view_data_preserves_analysis_half_width_kms(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Selected slices should preserve per-slice scientific analysis metadata."""
    slices = [
        VelocitySliceInfo(
            rest_wavelength=1215.67,
            label="Lyα 1215.67",
            tie_group_key="",
            line_id="lya",
            analysis_half_width_kms=300.0,
        ),
        VelocitySliceInfo(
            rest_wavelength=1550.0,
            label="CIV 1550",
            tie_group_key="",
            line_id="civ",
            analysis_half_width_kms=500.0,
        ),
        VelocitySliceInfo(
            rest_wavelength=2796.35, label="MgII 2796", tie_group_key="", line_id="mgii"
        ),
    ]
    for info in slices[:2]:
        info.selected = True

    _apply_slices(velocity_grid, slices)

    selected = velocity_grid.get_selected_slices()
    assert len(selected) == 2
    assert selected[0].analysis_half_width_kms == 300.0
    assert selected[1].analysis_half_width_kms == 500.0


def test_velocity_grid_refresh_preserves_explicit_deselection(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Refreshing view data should not reselect a user-deselected default slice."""
    slices = [
        VelocitySliceInfo(
            rest_wavelength=1215.67,
            label="Lyα 1215.67",
            tie_group_key="",
            line_id="lya",
            default_selected=True,
        ),
        VelocitySliceInfo(
            rest_wavelength=1548.0,
            label="C IV 1548",
            tie_group_key="",
            line_id="civ-1548",
            default_selected=True,
        ),
    ]
    _apply_slices(velocity_grid, slices, selection_scope_key="identify:candidate-a")
    subplots = _subplots(velocity_grid)

    subplots[0].set_checked(False)
    subplots[0].selection_toggled.emit(False)

    _apply_slices(
        velocity_grid,
        [
            VelocitySliceInfo(
                rest_wavelength=1215.67,
                label="Lyα 1215.67",
                tie_group_key="",
                line_id="lya",
                default_selected=True,
            ),
            VelocitySliceInfo(
                rest_wavelength=1548.0,
                label="C IV 1548",
                tie_group_key="",
                line_id="civ-1548",
                default_selected=True,
            ),
        ],
        selection_scope_key="identify:candidate-a",
    )

    assert [slice_info.selected for slice_info in velocity_grid.visible_slice_states()[:2]] == [
        False,
        True,
    ]
    assert subplots[0].is_checked() is False
    assert subplots[1].is_checked() is True


def test_velocity_grid_new_selection_scope_resets_to_default_selection(
    velocity_grid: VelocityGridWidget,
) -> None:
    """A different overlay scope should not inherit a prior manual deselection."""
    initial_slices = [
        VelocitySliceInfo(
            rest_wavelength=1215.67,
            label="Lyα 1215.67",
            tie_group_key="",
            line_id="lya",
            default_selected=True,
        )
    ]
    _apply_slices(velocity_grid, initial_slices, selection_scope_key="identify:candidate-a")
    subplots = _subplots(velocity_grid)

    subplots[0].set_checked(False)
    subplots[0].selection_toggled.emit(False)

    _apply_slices(
        velocity_grid,
        [
            VelocitySliceInfo(
                rest_wavelength=1215.67,
                label="Lyα 1215.67",
                tie_group_key="",
                line_id="lya",
                default_selected=True,
            )
        ],
        selection_scope_key="identify:candidate-b",
    )

    assert [slice_info.selected for slice_info in velocity_grid.visible_slice_states()[:1]] == [
        True
    ]
    assert subplots[0].is_checked() is True


def test_velocity_grid_new_selection_scope_resets_current_page(
    velocity_grid: VelocityGridWidget,
) -> None:
    """A different overlay scope should reopen from the first page."""
    initial_slices = [
        VelocitySliceInfo(
            rest_wavelength=5000.0 + index,
            label=f"Line {index}",
            tie_group_key="",
            line_id=f"line-{index}",
            default_selected=index == 0,
        )
        for index in range(8)
    ]
    _apply_slices(velocity_grid, initial_slices, selection_scope_key="identify:candidate-a")
    velocity_grid._set_page(1)

    replacement_slices = [
        VelocitySliceInfo(
            rest_wavelength=6000.0 + index,
            label=f"Other {index}",
            tie_group_key="",
            line_id=f"other-{index}",
            default_selected=index == 0,
        )
        for index in range(8)
    ]
    _apply_slices(velocity_grid, replacement_slices, selection_scope_key="identify:candidate-b")

    assert velocity_grid.pagination_state().current_page == 0
    assert [state.title for state in velocity_grid.visible_slice_states()[:3]] == [
        "Other 0",
        "Other 1",
        "Other 2",
    ]


def test_velocity_grid_renders_residual_in_optimize_mode(
    velocity_grid: VelocityGridWidget,
) -> None:
    """Optimize mode should make residual state visible when model data is present."""
    rest = 1_215.67
    z = 0.5
    rest_observed = rest * (1 + z)
    delta = rest_observed * 1e-4

    project = _velocity_view_project(
        observed_wavelength=np.array(
            [rest_observed - delta, rest_observed, rest_observed + delta]
        ),
        observed_flux=np.array([1.0, 0.9, 1.0]),
        observed_error=np.array([0.1, 0.1, 0.1]),
        model_wavelength=np.array([rest_observed - delta, rest_observed, rest_observed + delta]),
        model_flux=np.array([1.0, 0.95, 1.0]),
    )
    velocity_grid.set_mode("optimize")
    velocity_grid.apply_view_data(
        build_velocity_view_data(
            project,
            [
                VelocitySliceInfo(
                    rest_wavelength=rest,
                    label="Lyα 1215.67",
                    tie_group_key="",
                    center_z=z,
                    analysis_half_width_kms=150.0,
                )
            ],
            display_half_width_kms=velocity_grid.display_half_width.value,
            include_optimize_overlays=True,
        )
    )

    assert _subplots(velocity_grid)[0].render_state().residual_visible is True


@pytest.mark.parametrize("mode", ["identify", "optimize"])
def test_velocity_grid_omits_residual_without_model(
    velocity_grid: VelocityGridWidget, mode: str
) -> None:
    """Missing model data should leave residual state hidden in either mode."""
    velocity_grid.set_mode(mode)
    _apply_slices(
        velocity_grid,
        [
            VelocitySliceInfo(
                rest_wavelength=1_215.67, label="Lyα 1215.67", tie_group_key="", center_z=0.5
            )
        ],
        optimize=(mode == "optimize"),
    )

    assert _subplots(velocity_grid)[0].render_state().residual_visible is False


def _apply_slices(
    view: VelocityGridWidget,
    slices: list[VelocitySliceInfo],
    *,
    optimize: bool = False,
    selection_scope_key: str | None = None,
) -> None:
    """Apply slice-only view data without project spectra."""
    view.apply_view_data(
        build_velocity_view_data(
            None,
            slices,
            selection_scope_key=selection_scope_key,
            display_half_width_kms=view.display_half_width.value,
            include_optimize_overlays=optimize,
        )
    )


def _page_info(view: VelocityGridWidget) -> tuple[int, int]:
    """Return one-based pagination info from the grid."""
    page = view.pagination_state()
    return page.one_based_page, page.total_pages


def _subplots(view: VelocityGridWidget) -> tuple[VelocitySubplotWidget, ...]:
    """Return the subplot children in grid order."""
    return tuple(view._subplot_widgets)


def _velocity_view_project(
    *,
    observed_wavelength: np.ndarray,
    observed_flux: np.ndarray,
    observed_error: np.ndarray,
    model_wavelength: np.ndarray,
    model_flux: np.ndarray,
) -> SimpleNamespace:
    """Create project-like data for residual rendering tests."""
    return SimpleNamespace(
        model=SimpleNamespace(
            observed_spectrum=SimpleNamespace(
                wavelength=observed_wavelength, flux=observed_flux, error=observed_error
            ),
            model_spectrum=SimpleNamespace(wavelength=model_wavelength, flux=model_flux),
            mask_definitions=[],
        ),
        find_absorption_line=lambda _line_id: None,
        find_absorber_component=lambda _component_id: None,
    )
