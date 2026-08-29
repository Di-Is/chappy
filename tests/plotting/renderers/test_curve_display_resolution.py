"""Tests for the display-resolution decimation owner."""

from __future__ import annotations

import numpy as np

from chappy.plotting.renderers.curve_display_resolution import CurveDisplayResolutionOwner


class _RecordingSink:
    """Sink capturing display-data replacements per curve."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def set_curve_display_data(self, name: str, x: np.ndarray, y: np.ndarray) -> None:
        self.calls.append((name, len(x)))


def _make_owner(sink: _RecordingSink, *, target_bins: int = 100) -> CurveDisplayResolutionOwner:
    return CurveDisplayResolutionOwner(sink=sink, target_bins_provider=lambda: target_bins)


def _full_curve(n: int = 100_000) -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(1000.0, 2000.0, n)
    return x, np.ones(n)


def test_register_source_returns_decimated_arrays() -> None:
    """Registration decimates large sources over their full extent."""
    owner = _make_owner(_RecordingSink())
    x, y = _full_curve()

    display_x, display_y = owner.register_source("observed", x, y)

    assert len(display_x) == 200
    assert len(display_y) == 200


def test_register_small_source_passes_through() -> None:
    """Small sources are returned unchanged."""
    owner = _make_owner(_RecordingSink())
    x = np.linspace(0.0, 1.0, 50)

    display_x, _ = owner.register_source("model", x, x)

    np.testing.assert_array_equal(display_x, x)


def test_update_view_replaces_data_once_per_window() -> None:
    """Views inside the cached margin window do not trigger re-decimation."""
    sink = _RecordingSink()
    owner = _make_owner(sink)
    x, y = _full_curve()
    owner.register_source("observed", x, y)

    assert owner.update_view(1400.0, 1500.0) is True
    assert len(sink.calls) == 1

    # Small pan within the one-view-width margin: no recompute.
    assert owner.update_view(1420.0, 1520.0) is False
    assert len(sink.calls) == 1

    # Pan beyond the cached window: recompute.
    assert owner.update_view(1700.0, 1800.0) is True
    assert len(sink.calls) == 2


def test_update_view_recomputes_on_deep_zoom_in() -> None:
    """Zooming in well past the cached resolution re-decimates."""
    sink = _RecordingSink()
    owner = _make_owner(sink)
    x, y = _full_curve()
    owner.register_source("observed", x, y)
    owner.update_view(1000.0, 2000.0)

    assert owner.update_view(1400.0, 1450.0) is True


def test_update_view_without_sources_reports_no_redraw() -> None:
    """View updates with no registered curves need no redraw."""
    owner = _make_owner(_RecordingSink())

    assert owner.update_view(0.0, 1.0) is False


def test_update_view_ignores_invalid_ranges() -> None:
    """Degenerate or non-finite view ranges are ignored."""
    sink = _RecordingSink()
    owner = _make_owner(sink)
    x, y = _full_curve()
    owner.register_source("observed", x, y)

    assert owner.update_view(1500.0, 1500.0) is False
    assert owner.update_view(float("nan"), 1500.0) is False
    assert sink.calls == []


def test_source_and_unregister_roundtrip() -> None:
    """Registered full-resolution sources are retrievable until unregistered."""
    owner = _make_owner(_RecordingSink())
    x, y = _full_curve(1000)
    owner.register_source("observed", x, y)

    stored = owner.source("observed")
    assert stored is not None
    np.testing.assert_array_equal(stored[0], x)

    owner.unregister("observed")
    assert owner.source("observed") is None


def test_clear_drops_sources_and_window() -> None:
    """Clearing removes every source and resets the cached window."""
    sink = _RecordingSink()
    owner = _make_owner(sink)
    x, y = _full_curve()
    owner.register_source("observed", x, y)
    owner.update_view(1400.0, 1500.0)

    owner.clear()

    assert owner.source("observed") is None
    assert owner.update_view(1400.0, 1500.0) is False
