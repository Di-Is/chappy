"""Tests for the Matplotlib zoom overlay handle."""

from __future__ import annotations

from matplotlib.figure import Figure

from chappy.plotting.zoom_overlay_handle import ZoomOverlayHandle


class _StubCanvas:
    """Canvas stub recording draw requests."""

    def __init__(self) -> None:
        self.draw_idle_calls = 0

    def draw_idle(self) -> None:
        """Record an idle draw invocation."""
        self.draw_idle_calls += 1


def test_zoom_overlay_handle_updates_and_clears() -> None:
    """Ensure the overlay handle reuses a single patch and updates geometry."""
    figure = Figure()
    axes = figure.add_subplot(111)
    canvas = _StubCanvas()
    handle = ZoomOverlayHandle(axes=axes, canvas=canvas)

    handle.update((1.0, 2.0), (3.0, 5.0))

    assert handle.patch is not None
    assert len(axes.patches) == 1
    assert canvas.draw_idle_calls == 1

    patch = handle.patch
    assert patch is not None
    assert patch.get_x() == 1.0
    assert patch.get_y() == 2.0
    assert patch.get_width() == 2.0
    assert patch.get_height() == 3.0

    handle.update((3.0, 5.0), (0.0, 1.0))

    assert handle.patch is patch
    assert len(axes.patches) == 1
    assert canvas.draw_idle_calls == 2
    assert patch.get_x() == 0.0
    assert patch.get_y() == 1.0
    assert patch.get_width() == 3.0
    assert patch.get_height() == 4.0
    assert handle.start == (3.0, 5.0)
    assert handle.current == (0.0, 1.0)

    handle.clear()

    assert handle.patch is None
    assert handle.start is None
    assert handle.current is None
    assert canvas.draw_idle_calls == 3
    assert len(axes.patches) == 0
