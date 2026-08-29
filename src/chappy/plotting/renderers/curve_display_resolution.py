"""Owner for display-resolution decimation of registered spectrum curves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import numpy as np

from chappy.plotting.core.curve_decimation import DEFAULT_TARGET_BINS, decimate_to_envelope

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

REDECIMATE_ZOOM_IN_RATIO = 0.5


class CurveDisplayDataSink(Protocol):
    """Renderer API for replacing displayed curve vertices without rescaling axes."""

    def set_curve_display_data(
        self, name: str, x: NDArray[np.float64], y: NDArray[np.float64]
    ) -> None:
        """Replace the displayed vertices of an existing curve."""
        ...


@dataclass(frozen=True, slots=True)
class _CurveSource:
    """Full-resolution source arrays for one registered curve."""

    x: NDArray[np.float64]
    y: NDArray[np.float64]


class CurveDisplayResolutionOwner:
    """Keep full-resolution curve sources and apply viewport-sized envelopes.

    Registered curve artists hold a display-resolution slice, not the true
    data. Full-resolution arrays live here and in ``SpectrumPlotDataStore``;
    code that needs real data must not read it back from the artists.
    """

    def __init__(
        self, *, sink: CurveDisplayDataSink, target_bins_provider: Callable[[], int] | None = None
    ) -> None:
        """Initialize the owner.

        Args:
            sink: Renderer receiving decimated display data.
            target_bins_provider: Provider for the envelope bin count, typically
                derived from the canvas pixel width. Defaults to a fixed count.
        """
        self._sink = sink
        self._target_bins_provider = target_bins_provider or (lambda: DEFAULT_TARGET_BINS)
        self._sources: dict[str, _CurveSource] = {}
        self._view: tuple[float, float] | None = None
        self._window: tuple[float, float] | None = None

    def register_source(
        self, name: str, x: NDArray[np.float64], y: NDArray[np.float64]
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Register full-resolution source arrays for a curve.

        Args:
            name: Curve identifier matching the renderer's curve name.
            x: Full-resolution x values, sorted ascending.
            y: Full-resolution y values.

        Returns:
            Display-resolution arrays covering the full data extent.
        """
        # New data invalidates the cached view window: axis limits at render
        # time may still describe the previous dataset (or the initial axes).
        self._view = None
        self._window = None
        self._sources[name] = _CurveSource(x=x, y=y)
        return self._decimate(self._sources[name])

    def source(self, name: str) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
        """Return the registered full-resolution arrays for a curve."""
        registered = self._sources.get(name)
        if registered is None:
            return None
        return registered.x, registered.y

    def unregister(self, name: str) -> None:
        """Drop the registered source for a removed curve."""
        self._sources.pop(name, None)

    def clear(self) -> None:
        """Drop all registered sources and the cached view window."""
        self._sources.clear()
        self._view = None
        self._window = None

    def update_view(self, view_min: float, view_max: float) -> bool:
        """Re-decimate registered curves for a new visible x-range.

        Args:
            view_min: Visible x-range minimum.
            view_max: Visible x-range maximum.

        Returns:
            True when curve display data was replaced and a redraw is needed.
        """
        if view_max <= view_min or not np.isfinite(view_min) or not np.isfinite(view_max):
            return False
        if not self._needs_redecimation(view_min, view_max):
            return False

        margin = view_max - view_min
        self._view = (view_min, view_max)
        self._window = (view_min - margin, view_max + margin)
        for name, registered in self._sources.items():
            display_x, display_y = self._decimate(registered)
            self._sink.set_curve_display_data(name, display_x, display_y)
        return bool(self._sources)

    def _needs_redecimation(self, view_min: float, view_max: float) -> bool:
        if self._view is None or self._window is None:
            return True
        if view_min < self._window[0] or view_max > self._window[1]:
            return True
        cached_width = self._view[1] - self._view[0]
        return (view_max - view_min) < cached_width * REDECIMATE_ZOOM_IN_RATIO

    def _decimate(
        self, registered: _CurveSource
    ) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        if len(registered.x) == 0:
            return registered.x, registered.y
        target_bins = self._target_bins_provider()
        if self._window is not None and self._view is not None:
            window_min, window_max = self._window
            # The margin window spans multiple view widths; scale the bin count
            # so the visible portion keeps full per-pixel resolution.
            view_width = self._view[1] - self._view[0]
            ratio = (window_max - window_min) / view_width
            target_bins = int(target_bins * min(ratio, 4.0))
        else:
            window_min, window_max = float(registered.x[0]), float(registered.x[-1])
        return decimate_to_envelope(
            registered.x,
            registered.y,
            window_min=window_min,
            window_max=window_max,
            target_bins=target_bins,
        )
