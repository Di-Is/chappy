"""Min/max envelope decimation for display-resolution curve rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

DEFAULT_TARGET_BINS: Final = 1500
PASSTHROUGH_BIN_MULTIPLIER: Final = 4


def decimate_to_envelope(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    window_min: float,
    window_max: float,
    target_bins: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return a display slice of ``(x, y)`` covering ``[window_min, window_max]``.

    ``x`` must be sorted ascending, except for NaN entries used as segment
    separators (windowed model/residual curves interleave NaN gap markers).
    The slice keeps one extra sample on each side so line segments reach the
    window edges. Slices small enough to draw directly are returned unchanged;
    larger slices are reduced to a per-bin min/max envelope, which preserves
    narrow absorption and emission spikes exactly. All-NaN bins stay NaN so
    masked gaps are not bridged.

    Args:
        x: Full-resolution x values, sorted ascending aside from NaN separators.
        y: Full-resolution y values.
        window_min: Lower bound of the wavelength window to cover.
        window_max: Upper bound of the wavelength window to cover.
        target_bins: Number of envelope bins; the decimated output has two
            points per bin.

    Returns:
        Display-resolution ``(x, y)`` arrays.
    """
    if target_bins < 1:
        msg = f"target_bins must be positive, got {target_bins}"
        raise ValueError(msg)

    # Mask-based bounds instead of searchsorted: interior NaN separators break
    # binary search and would silently drop later segments.
    inside = np.flatnonzero((x >= window_min) & (x <= window_max))
    if inside.size > 0:
        start = max(int(inside[0]) - 1, 0)
        stop = min(int(inside[-1]) + 2, len(x))
    else:
        # No sample falls inside the window (view narrower than the sample
        # spacing): keep the bracketing samples so the connecting segment,
        # or a NaN gap, still renders across the view.
        finite = np.flatnonzero(np.isfinite(x))
        if finite.size == 0:
            return x[:0], y[:0]
        position = int(np.searchsorted(x[finite], window_min, side="left"))
        start = int(finite[max(position - 1, 0)])
        stop = int(finite[min(position, finite.size - 1)]) + 1
    x_slice = x[start:stop]
    y_slice = y[start:stop]

    if len(x_slice) <= PASSTHROUGH_BIN_MULTIPLIER * target_bins:
        return x_slice, y_slice

    edges = (np.arange(target_bins, dtype=np.intp) * len(x_slice)) // target_bins
    # fmin/fmax ignore NaN unless a whole bin is NaN, preserving masked gaps.
    y_min = np.fmin.reduceat(y_slice, edges)
    y_max = np.fmax.reduceat(y_slice, edges)

    x_out = np.repeat(x_slice[edges], 2)
    y_out = np.empty(2 * target_bins, dtype=np.float64)
    y_out[0::2] = y_min
    y_out[1::2] = y_max
    return x_out, y_out
