"""Tests for velocity grid pagination presenter."""

from __future__ import annotations

import pytest

from chappy.presentation.velocity import (
    MAX_VELOCITY_SUBPLOTS,
    VelocityGridPresenter,
    compute_velocity_grid_capacity,
    compute_velocity_grid_shape,
)


@pytest.mark.parametrize(
    ("cell_count", "expected"),
    [(0, (1, 1)), (1, (1, 1)), (2, (1, 2)), (3, (2, 2)), (4, (2, 2)), (5, (2, 3)), (6, (2, 3))],
)
def test_compute_velocity_grid_shape_legacy_capacity(
    cell_count: int, expected: tuple[int, int]
) -> None:
    """Grid shape should track the visible slice count without empty rows."""
    rows, columns = compute_velocity_grid_shape(cell_count, max_rows=2, max_columns=3)
    assert (rows, columns) == expected
    assert rows * columns >= cell_count


@pytest.mark.parametrize(
    ("cell_count", "max_rows", "max_columns", "expected"),
    [
        (7, 2, 4, (2, 4)),
        (8, 2, 4, (2, 4)),
        (9, 3, 3, (3, 3)),
        (9, 3, 4, (3, 3)),
        (12, 3, 4, (3, 4)),
        (5, 3, 2, (3, 2)),
        (3, 1, 4, (1, 3)),
        (20, 3, 4, (3, 4)),
    ],
)
def test_compute_velocity_grid_shape_extended_capacity(
    cell_count: int, max_rows: int, max_columns: int, expected: tuple[int, int]
) -> None:
    """Grid shape should extend to larger capacities while respecting the row/column limits."""
    rows, columns = compute_velocity_grid_shape(
        cell_count, max_rows=max_rows, max_columns=max_columns
    )
    assert (rows, columns) == expected
    assert rows <= max_rows
    assert columns <= max_columns


@pytest.mark.parametrize(
    ("width_px", "height_px", "expected"),
    [
        (0, 0, (1, 1)),
        (239, 169, (1, 1)),
        (480, 340, (2, 2)),
        (720, 340, (2, 3)),
        (960, 510, (3, 4)),
        (5000, 5000, (3, 4)),
    ],
)
def test_compute_velocity_grid_capacity(
    width_px: int, height_px: int, expected: tuple[int, int]
) -> None:
    """Capacity should follow the pixel area within the fixed row/column limits."""
    rows, columns = compute_velocity_grid_capacity(width_px=width_px, height_px=height_px)
    assert (rows, columns) == expected
    assert rows * columns <= MAX_VELOCITY_SUBPLOTS


def test_velocity_grid_presenter_clamps_requested_page() -> None:
    """Requested pages outside the valid range should be clamped."""
    presenter = VelocityGridPresenter()

    page = presenter.build_page(slice_count=8, subplot_count=6, requested_page=3)

    assert page.current_page == 1
    assert page.total_pages == 2
    assert page.start_index == 6
    assert page.end_index == 8
    assert page.visible_count == 2
    assert page.slot_number(0) == 7


def test_velocity_grid_presenter_handles_empty_slices() -> None:
    """Empty grids should have no display page."""
    presenter = VelocityGridPresenter()

    page = presenter.build_page(slice_count=0, subplot_count=6, requested_page=1)

    assert page.current_page == 0
    assert page.one_based_page == 0
    assert page.total_pages == 0
    assert page.visible_count == 0
