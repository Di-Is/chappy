"""Feedback overlay renderer for continuum editor interactions."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from matplotlib.lines import Line2D

if TYPE_CHECKING:
    from matplotlib.artist import Artist
    from matplotlib.axes import Axes

DisplayPointResolver = Callable[[float, float], tuple[float, float] | None]
FeedbackScheduler = Callable[[int, Callable[[], None]], None]


class ContinuumFeedbackRenderer:
    """Render transient feedback markers for invalid continuum operations."""

    def __init__(
        self, *, hit_radius_px: int, z_order: float, scheduler: FeedbackScheduler | None = None
    ) -> None:
        """Initialise the renderer.

        Args:
            hit_radius_px: Half-size of the feedback cross in display pixels.
            z_order: Matplotlib z-order for the feedback artists.
            scheduler: Optional callback scheduler for transient marker cleanup.
        """
        self._hit_radius_px = hit_radius_px
        self._z_order = z_order
        self._scheduler = scheduler

    def show_cross(
        self,
        *,
        point: tuple[float, float],
        axes: Axes,
        data_to_display: DisplayPointResolver,
        display_to_data: DisplayPointResolver,
        artists: list[Artist],
        clear_callback: Callable[[], None],
    ) -> None:
        """Draw a transient cross centered on a data-space point."""
        display_point = data_to_display(*point)
        if display_point is None:
            return

        self.clear(artists)
        size = self._hit_radius_px
        for dx1, dy1, dx2, dy2 in [(-size, -size, size, size), (-size, size, size, -size)]:
            start = display_to_data(display_point[0] + dx1, display_point[1] + dy1)
            end = display_to_data(display_point[0] + dx2, display_point[1] + dy2)
            if start is None or end is None:
                continue
            line = Line2D(
                [start[0], end[0]],
                [start[1], end[1]],
                color="#DC3545",
                linewidth=1.5,
                zorder=self._z_order,
            )
            axes.add_line(line)
            artists.append(line)
        axes.figure.canvas.draw_idle()
        if self._scheduler is not None:
            self._scheduler(1200, clear_callback)

    @staticmethod
    def clear(artists: list[Artist]) -> None:
        """Remove feedback artists from their axes."""
        for artist in list(artists):
            artist.remove()
        artists.clear()
