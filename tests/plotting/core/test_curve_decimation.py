"""Tests for min/max envelope curve decimation."""

from __future__ import annotations

import numpy as np
import pytest

from chappy.plotting.core.curve_decimation import PASSTHROUGH_BIN_MULTIPLIER, decimate_to_envelope


def test_small_slice_passes_through_unchanged() -> None:
    """Slices at or below the passthrough threshold keep every sample."""
    x = np.linspace(1000.0, 1100.0, 50)
    y = np.sin(x)

    out_x, out_y = decimate_to_envelope(x, y, window_min=990.0, window_max=1110.0, target_bins=100)

    np.testing.assert_array_equal(out_x, x)
    np.testing.assert_array_equal(out_y, y)


def test_window_slice_keeps_one_sample_beyond_each_edge() -> None:
    """The slice extends one sample past the window so lines reach the edges."""
    x = np.arange(0.0, 100.0)
    y = np.arange(0.0, 100.0)

    out_x, _ = decimate_to_envelope(x, y, window_min=10.5, window_max=20.5, target_bins=100)

    assert out_x[0] == 10.0
    assert out_x[-1] == 21.0


def test_envelope_preserves_extremes() -> None:
    """Decimation must keep global min/max and narrow spikes exactly."""
    rng = np.random.default_rng(0)
    n = 100_000
    x = np.linspace(1000.0, 2000.0, n)
    y = 1.0 + 0.01 * rng.standard_normal(n)
    y[41_234] = -5.0
    y[77_777] = 9.0

    out_x, out_y = decimate_to_envelope(
        x, y, window_min=1000.0, window_max=2000.0, target_bins=1000
    )

    assert len(out_x) == 2000
    assert float(np.min(out_y)) == -5.0
    assert float(np.max(out_y)) == 9.0


def test_envelope_output_size_scales_with_bins() -> None:
    """The envelope emits two points per bin above the passthrough threshold."""
    n = PASSTHROUGH_BIN_MULTIPLIER * 100 + 1
    x = np.linspace(0.0, 1.0, n)
    y = np.zeros(n)

    out_x, out_y = decimate_to_envelope(x, y, window_min=0.0, window_max=1.0, target_bins=100)

    assert len(out_x) == 200
    assert len(out_y) == 200


def test_all_nan_bins_stay_nan() -> None:
    """Masked gaps must not be bridged by the envelope."""
    n = 10_000
    x = np.linspace(0.0, 1.0, n)
    y = np.ones(n)
    y[4000:6000] = np.nan

    _, out_y = decimate_to_envelope(x, y, window_min=0.0, window_max=1.0, target_bins=1000)

    assert np.any(np.isnan(out_y))
    assert float(np.nanmin(out_y)) == 1.0


def test_nan_separated_segments_are_both_kept() -> None:
    """Windowed doublet curves with interior NaN separators must keep every segment."""
    seg1 = np.linspace(6190.0, 6194.0, 50)
    seg2 = np.linspace(6200.0, 6204.0, 50)
    x = np.concatenate([seg1, [np.nan], seg2])
    y = np.concatenate([np.full(50, 0.5), [np.nan], np.full(50, 0.8)])

    out_x, out_y = decimate_to_envelope(
        x, y, window_min=6180.0, window_max=6210.0, target_bins=100
    )

    finite = np.isfinite(out_x)
    assert out_x[finite].min() <= 6190.0
    assert out_x[finite].max() >= 6204.0
    assert np.any(out_y[finite] == 0.8), "second segment must survive"
    assert np.any(np.isnan(out_x)), "gap separator must be preserved"


def test_view_between_samples_keeps_bracketing_points() -> None:
    """A window narrower than the sample spacing keeps the bracketing samples."""
    x = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([10.0, 20.0, 30.0, 40.0])

    out_x, out_y = decimate_to_envelope(x, y, window_min=2.2, window_max=2.8, target_bins=100)

    np.testing.assert_array_equal(out_x, [2.0, 3.0])
    np.testing.assert_array_equal(out_y, [20.0, 30.0])


def test_empty_input_returns_empty() -> None:
    """Empty source arrays decimate to empty display arrays."""
    empty = np.array([], dtype=np.float64)

    out_x, out_y = decimate_to_envelope(
        empty, empty, window_min=0.0, window_max=1.0, target_bins=10
    )

    assert len(out_x) == 0
    assert len(out_y) == 0


def test_invalid_target_bins_raises() -> None:
    """Non-positive bin counts are a caller error."""
    x = np.linspace(0.0, 1.0, 10)

    with pytest.raises(ValueError, match="target_bins"):
        decimate_to_envelope(x, x, window_min=0.0, window_max=1.0, target_bins=0)
