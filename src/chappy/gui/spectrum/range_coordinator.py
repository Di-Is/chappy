"""Coordinate spectrum wavelength and flux range updates."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from math import isclose
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from chappy.gui.spectrum.spectrum_data_bridge import SpectrumDataBridge
    from chappy.gui.spectrum.spectrum_plot import SpectrumPlotHost

logger = logging.getLogger(__name__)


class RangeInputSyncPort(Protocol):
    """Optional input component that mirrors coordinated range values."""

    def set_wavelength_range(self, min_wave: float, max_wave: float) -> None:
        """Mirror the wavelength range into the input component."""
        ...

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Mirror the flux range into the input component."""
        ...


class RangeHistoryRecorder(Protocol):
    """Range change recording required by coordinated range updates."""

    def record_range_change(
        self,
        old_wave_range: tuple[float, float],
        new_wave_range: tuple[float, float],
        old_flux_range: tuple[float, float] | None,
        new_flux_range: tuple[float, float] | None,
        source: str,
    ) -> None:
        """Record a range change event to history."""
        ...


class RangeCoordinator:
    """Synchronize spectrum ranges across state, plot, optional inputs, and history."""

    def __init__(
        self,
        *,
        data_bridge_provider: Callable[[], SpectrumDataBridge | None],
        plot_host_provider: Callable[[], SpectrumPlotHost | None],
        range_input_provider: Callable[[], RangeInputSyncPort | None],
        history_recorder_provider: Callable[[], RangeHistoryRecorder | None],
        flux_range_override_provider: Callable[[], tuple[float, float] | None],
    ) -> None:
        """Initialize the coordinator.

        Args:
            data_bridge_provider: Provider for the current data bridge.
            plot_host_provider: Provider for the current plot host.
            range_input_provider: Provider for optional range input synchronization.
            history_recorder_provider: Provider for undo history integration.
            flux_range_override_provider: Provider for a flux range that takes
                precedence over data-derived auto ranges, or None when absent.
        """
        self._data_bridge_provider = data_bridge_provider
        self._plot_host_provider = plot_host_provider
        self._range_input_provider = range_input_provider
        self._history_recorder_provider = history_recorder_provider
        self._flux_range_override_provider = flux_range_override_provider
        self._auto_adjust_y_enabled = False
        self._applying_update = False

    @contextmanager
    def _suppress_bridge_echo(self) -> Iterator[None]:
        """Mark coordinator-driven updates so synchronous bridge echoes are dropped.

        Data-bridge writes below emit ``range_changed`` synchronously, which
        routes back into ``handle_data_bridge_range_changed``; without this
        guard every update runs its plot/input synchronization multiple times.
        """
        previous = self._applying_update
        self._applying_update = True
        try:
            yield
        finally:
            self._applying_update = previous

    def coordinate_range_update(
        self,
        source: str,
        min_wave: float,
        max_wave: float,
        *,
        flux_range: tuple[float, float] | None = None,
        record_history: bool = True,
        old_wave_range: tuple[float, float] | None = None,
        old_flux_range: tuple[float, float] | None = None,
    ) -> None:
        """Coordinate wavelength range updates between components.

        Args:
            source: Component or interaction source initiating the update.
            min_wave: Minimum wavelength.
            max_wave: Maximum wavelength.
            flux_range: Optional flux range to synchronize atomically.
            record_history: Whether to record this change in undo history.
            old_wave_range: Optional previous wavelength range for history.
            old_flux_range: Optional previous flux range for history.
        """
        logger.debug(
            "Coordinating range update from %s: wave=%.2f-%.2f, flux=%s",
            source,
            min_wave,
            max_wave,
            flux_range,
        )

        if old_wave_range is None:
            old_wave_range = self.get_current_wavelength_range()
        if old_flux_range is None and flux_range is not None:
            old_flux_range = self.get_current_flux_range()

        data_bridge = self._data_bridge_provider()
        if data_bridge is None:
            msg = "Data bridge is required for coordinated range updates."
            raise RuntimeError(msg)

        with self._suppress_bridge_echo():
            if source != "data_bridge":
                data_bridge.set_wavelength_range(min_wave, max_wave)
                if flux_range:
                    data_bridge.set_flux_range(flux_range[0], flux_range[1])

            plot = self._plot_host_provider()
            if plot is None:
                msg = "Plot host is required for coordinated range updates."
                raise RuntimeError(msg)

            if source != "plot":
                if flux_range:
                    plot.set_plot_range(min_wave, max_wave, flux_range[0], flux_range[1])
                else:
                    plot.set_wavelength_range(min_wave, max_wave)

                if (
                    flux_range is None
                    and self._auto_adjust_y_enabled
                    and source not in {"data_bridge", "intent", "interactor"}
                ):
                    logger.debug("Auto-adjusting Y-axis for new X range")
                    plot.auto_range_flux()
                    self.sync_flux_from_plot(source)

            range_input = self._range_input_provider()
            if range_input and source != "range_input":
                range_input.set_wavelength_range(min_wave, max_wave)
                if flux_range:
                    range_input.set_flux_range(flux_range[0], flux_range[1])

        should_record = (
            record_history
            and self._history_recorder_provider() is not None
            and source not in {"group-selection", "data_bridge"}
        )
        if should_record:
            self._record_range_change(
                old_wave_range, (min_wave, max_wave), old_flux_range, flux_range, source
            )

    def get_current_wavelength_range(self) -> tuple[float, float]:
        """Get the current wavelength range for history recording."""
        data_bridge = self._data_bridge_provider()
        if data_bridge:
            return data_bridge.get_wavelength_range()

        plot = self._plot_host_provider()
        if plot:
            xmin, xmax, _, _ = plot.get_plot_range()
            return (xmin, xmax)
        msg = "Current wavelength range is required but no data or plot host is available."
        raise RuntimeError(msg)

    def get_current_flux_range(self) -> tuple[float, float]:
        """Get the current flux range for history recording."""
        data_bridge = self._data_bridge_provider()
        if data_bridge:
            return data_bridge.get_flux_range()

        plot = self._plot_host_provider()
        if plot:
            _, _, ymin, ymax = plot.get_plot_range()
            return (ymin, ymax)
        msg = "Current flux range is required but no data or plot host is available."
        raise RuntimeError(msg)

    def sync_flux_from_plot(self, origin: str) -> None:
        """Persist the current plot flux range back to data bridge and controls."""
        auto_range = self.calculate_auto_flux_range()
        if not auto_range:
            logger.debug("Auto-adjust sync skipped; unable to derive flux range from data")
            return

        min_flux, max_flux = auto_range
        data_bridge = self._data_bridge_provider()
        if data_bridge and origin != "data_bridge":
            current_min, current_max = data_bridge.get_flux_range()
            if not self._flux_ranges_close((current_min, current_max), (min_flux, max_flux)):
                with self._suppress_bridge_echo():
                    data_bridge.set_flux_range(min_flux, max_flux)
            return

        self._sync_flux_inputs(min_flux, max_flux)

    def calculate_auto_flux_range(self) -> tuple[float, float] | None:
        """Compute flux auto-range for the current visible wavelength window."""
        data_bridge = self._data_bridge_provider()
        if data_bridge is None:
            msg = "Data bridge is required for automatic flux range calculation."
            raise RuntimeError(msg)

        spectrum = data_bridge.get_spectrum_data()
        if not spectrum:
            return None

        wavelength, flux, _ = spectrum
        if wavelength is None or flux is None:
            return None

        wave_array = np.asarray(wavelength)
        flux_array = np.asarray(flux)
        if wave_array.size == 0 or flux_array.size == 0:
            return None

        min_wave, max_wave = data_bridge.get_wavelength_range()
        mask = (wave_array >= min_wave) & (wave_array <= max_wave)
        if not np.any(mask):
            return None

        visible_flux = flux_array[mask]
        if visible_flux.size == 0:
            return None

        y_min = float(np.min(visible_flux))
        y_max = float(np.max(visible_flux))
        label_y_position = 0.92
        new_y_min = min(y_min - 0.05, -0.05)
        required_plot_range = (y_max - new_y_min) / label_y_position
        new_y_max = max(new_y_min + required_plot_range, 1.05)

        if isclose(new_y_min, new_y_max, rel_tol=0.0, abs_tol=1e-9):
            new_y_max = new_y_min + 1.0

        return new_y_min, new_y_max

    def apply_flux_update(
        self,
        source: str,
        min_flux: float,
        max_flux: float,
        min_wave: float | None = None,
        max_wave: float | None = None,
    ) -> None:
        """Propagate flux range updates to plot and optional input widgets."""
        if source == "range_input":
            self.disable_auto_adjust_y()

        plot = self._plot_host_provider()
        if plot and source != "plot":
            if min_wave is not None and max_wave is not None:
                plot.set_plot_range(min_wave, max_wave, min_flux, max_flux)
            else:
                plot.set_flux_range(min_flux, max_flux)

        range_input = self._range_input_provider()
        if range_input and source != "range_input":
            range_input.set_flux_range(min_flux, max_flux)

    def handle_auto_flux_range_request(self) -> None:
        """Handle auto flux range requests and enable auto-adjust mode."""
        logger.debug("Auto flux range requested - enabling auto-adjust mode")
        self._auto_adjust_y_enabled = True

        override_range = self._flux_range_override_provider()
        if override_range:
            min_flux, max_flux = override_range
            logger.debug("Using flux range override: min=%s, max=%s", min_flux, max_flux)
        else:
            auto_range = self.calculate_auto_flux_range()
            if auto_range:
                min_flux, max_flux = auto_range
            else:
                plot = self._plot_host_provider()
                if plot:
                    plot.auto_range_flux()
                    self.sync_flux_from_plot("auto_button")
                return

        current_wave = self.get_current_wavelength_range()
        self.coordinate_range_update(
            source="auto_adjust",
            min_wave=current_wave[0],
            max_wave=current_wave[1],
            flux_range=(min_flux, max_flux),
        )

    def disable_auto_adjust_y(self) -> None:
        """Disable automatic Y-axis adjustment."""
        if self._auto_adjust_y_enabled:
            logger.debug("Disabling auto-adjust Y mode")
            self._auto_adjust_y_enabled = False

    def reset_view_ranges(
        self,
        *,
        wavelength_range: tuple[float, float] | None = None,
        flux_range: tuple[float, float] | None = None,
    ) -> None:
        """Reset coordinated spectrum ranges using optional explicit bounds."""
        data_bridge = self._data_bridge_provider()
        if data_bridge is None:
            msg = "Data bridge is required for resetting view ranges."
            raise RuntimeError(msg)

        if wavelength_range is None:
            self.auto_scale()
            return

        min_wave, max_wave = float(wavelength_range[0]), float(wavelength_range[1])
        self.disable_auto_adjust_y()
        self.coordinate_range_update("reset", min_wave, max_wave)

        if flux_range is not None:
            min_flux = float(flux_range[0])
            max_flux = float(flux_range[1])
        else:
            plot_flux_range = self._plot_flux_range()
            if plot_flux_range is None:
                self.sync_flux_from_plot("reset")
                return
            min_flux, max_flux = plot_flux_range

        with self._suppress_bridge_echo():
            data_bridge.set_flux_range(min_flux, max_flux)
        self.apply_flux_update("reset", min_flux, max_flux, min_wave=min_wave, max_wave=max_wave)

    def handle_data_bridge_range_changed(
        self, min_wave: float, max_wave: float, min_flux: float, max_flux: float
    ) -> None:
        """Synchronize components after a data-bridge range change."""
        if self._applying_update:
            return
        self.coordinate_range_update("data_bridge", min_wave, max_wave)
        self.apply_flux_update(
            "data_bridge", min_flux, max_flux, min_wave=min_wave, max_wave=max_wave
        )

    def auto_scale(self) -> None:
        """Auto-scale data, apply renderer margins, and sync final ranges."""
        logger.debug("Auto-scale requested")
        data_bridge = self._data_bridge_provider()
        if data_bridge is None:
            msg = "Data bridge is required for auto-scaling ranges."
            raise RuntimeError(msg)

        old_wave_range = self.get_current_wavelength_range()
        old_flux_range = self.get_current_flux_range()
        with self._suppress_bridge_echo():
            data_bridge.auto_scale_ranges()

        plot = self._plot_host_provider()
        if plot is None:
            msg = "Plot host is required for auto-scaling ranges."
            raise RuntimeError(msg)

        # Seed the plot with data-derived ranges before auto-ranging: at project
        # load the plot may hold no curves yet, and auto-ranging an empty plot
        # would report default axis limits back into the bridge.
        min_wave, max_wave = data_bridge.get_wavelength_range()
        min_flux, max_flux = data_bridge.get_flux_range()
        plot.set_plot_range(min_wave, max_wave, min_flux, max_flux)

        logger.debug("Calling auto_range_all on plot")
        plot.auto_range_all()
        if not plot.has_valid_renderer():
            msg = "Renderer is required for auto-scaling ranges."
            raise RuntimeError(msg)

        x_min, x_max, y_min, y_max = plot.get_plot_range()
        logger.debug(
            "Syncing final ranges: x=[%.1f, %.1f], y=[%.3f, %.3f]", x_min, x_max, y_min, y_max
        )
        self.coordinate_range_update(
            source="auto_scale",
            min_wave=x_min,
            max_wave=x_max,
            flux_range=(y_min, y_max),
            old_wave_range=old_wave_range,
            old_flux_range=old_flux_range,
        )

    def _record_range_change(
        self,
        old_wave_range: tuple[float, float],
        new_wave_range: tuple[float, float],
        old_flux_range: tuple[float, float] | None,
        new_flux_range: tuple[float, float] | None,
        source: str,
    ) -> None:
        """Record a range change event to history."""
        history_recorder = self._history_recorder_provider()
        if not history_recorder:
            logger.debug("History recorder not set, skipping range change recording")
            return

        history_recorder.record_range_change(
            old_wave_range, new_wave_range, old_flux_range, new_flux_range, source
        )

    @staticmethod
    def _flux_ranges_close(
        current: tuple[float, float],
        updated: tuple[float, float],
        *,
        rel_tol: float = 1e-6,
        abs_tol: float = 1e-6,
    ) -> bool:
        """Return True when two flux ranges are effectively identical."""
        return isclose(current[0], updated[0], rel_tol=rel_tol, abs_tol=abs_tol) and isclose(
            current[1], updated[1], rel_tol=rel_tol, abs_tol=abs_tol
        )

    def _sync_flux_inputs(self, min_flux: float, max_flux: float) -> None:
        """Update range input widgets without modifying plot limits."""
        range_input = self._range_input_provider()
        if range_input:
            range_input.set_flux_range(min_flux, max_flux)

    def _plot_flux_range(self) -> tuple[float, float] | None:
        """Return a valid flux range from the plot host."""
        plot = self._plot_host_provider()
        if not plot:
            return None

        _, _, y_min, y_max = plot.get_plot_range()
        if y_min >= y_max:
            return None
        return float(y_min), float(y_max)
