"""Pure presenter for velocity subplot pagination."""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_VELOCITY_CELL_WIDTH_PX = 240
MIN_VELOCITY_CELL_HEIGHT_PX = 170
MAX_VELOCITY_GRID_ROWS = 3
MAX_VELOCITY_GRID_COLUMNS = 4
MAX_VELOCITY_SUBPLOTS = MAX_VELOCITY_GRID_ROWS * MAX_VELOCITY_GRID_COLUMNS


def compute_velocity_grid_capacity(*, width_px: int, height_px: int) -> tuple[int, int]:
    """Return the (max_rows, max_columns) of minimum-size cells fitting the pixel area."""
    rows = max(1, min(height_px // MIN_VELOCITY_CELL_HEIGHT_PX, MAX_VELOCITY_GRID_ROWS))
    columns = max(1, min(width_px // MIN_VELOCITY_CELL_WIDTH_PX, MAX_VELOCITY_GRID_COLUMNS))
    return (rows, columns)


def compute_velocity_grid_shape(
    cell_count: int, *, max_rows: int, max_columns: int
) -> tuple[int, int]:
    """Return the (rows, columns) grid shape that fits ``cell_count`` subplots."""
    count = max(1, min(cell_count, max_rows * max_columns))
    candidates = [
        (math.ceil(count / columns), columns)
        for columns in range(1, max_columns + 1)
        if math.ceil(count / columns) <= max_rows
    ]
    return min(
        candidates,
        key=lambda shape: (abs(shape[0] - shape[1]), shape[0] * shape[1] - count, shape[0]),
    )


@dataclass(frozen=True, slots=True)
class VelocityGridPage:
    """Computed pagination state for the velocity subplot grid."""

    current_page: int
    total_pages: int
    page_size: int
    start_index: int
    end_index: int
    visible_count: int

    @property
    def one_based_page(self) -> int:
        """Return the display page number."""
        if self.total_pages == 0:
            return 0
        return self.current_page + 1

    def slot_number(self, local_index: int) -> int:
        """Return the one-based slot number for a subplot index."""
        return self.current_page * self.page_size + local_index + 1

    def absolute_index(self, local_index: int) -> int:
        """Return the slice index represented by a local subplot index."""
        return self.current_page * self.page_size + local_index

    def local_index(self, absolute_index: int) -> int | None:
        """Return the local subplot index for a visible absolute index."""
        local_index = absolute_index - self.start_index
        if 0 <= local_index < self.page_size:
            return local_index
        return None


class VelocityGridPresenter:
    """Calculate velocity grid pages without touching Qt widgets."""

    def build_page(
        self, *, slice_count: int, subplot_count: int, requested_page: int
    ) -> VelocityGridPage:
        """Return clamped pagination state for the current grid."""
        page_size = max(1, subplot_count)
        if slice_count <= 0:
            return VelocityGridPage(
                current_page=0,
                total_pages=0,
                page_size=page_size,
                start_index=0,
                end_index=0,
                visible_count=0,
            )

        total_pages = math.ceil(slice_count / page_size)
        current_page = max(0, min(requested_page, total_pages - 1))
        start_index = current_page * page_size
        end_index = min(start_index + page_size, slice_count)
        return VelocityGridPage(
            current_page=current_page,
            total_pages=total_pages,
            page_size=page_size,
            start_index=start_index,
            end_index=end_index,
            visible_count=end_index - start_index,
        )
