"""Test fixtures for spectrum presenter dependencies."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject


class MockSignal:
    """Simple Qt-like signal helper for tests."""

    def __init__(self) -> None:
        """Initialize signal with empty subscriber list."""
        self._subscribers: list[Callable[..., None]] = []

    def connect(self, callback: Callable[..., None]) -> None:
        """Register a callback.

        Args:
            callback: Callback invoked when the signal is emitted.
        """
        self._subscribers.append(callback)

    def disconnect(self, callback: Callable[..., None]) -> None:
        """Unregister a callback.

        Args:
            callback: Callback to remove from the subscriber list.
        """
        with contextlib.suppress(ValueError):
            self._subscribers.remove(callback)

    def emit(self, *args, **kwargs) -> None:
        """Emit the signal to all subscribers.

        Args:
            *args: Positional arguments forwarded to subscribers.
            **kwargs: Keyword arguments forwarded to subscribers.
        """
        for callback in list(self._subscribers):
            callback(*args, **kwargs)


@dataclass(slots=True)
class MockSpectrumDataBridge:
    """Lightweight stand-in for SpectrumDataBridge used in tests."""

    project: object | None = None
    _wavelength_range: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    _flux_range: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    _spectrum: tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]] | None = None
    auto_scale_ranges_called: bool = False
    project_changed: MockSignal = field(default_factory=MockSignal)
    data_updated: MockSignal = field(default_factory=MockSignal)
    range_changed: MockSignal = field(default_factory=MockSignal)

    def set_wavelength_range(self, minimum: float, maximum: float) -> None:
        """Persist the wavelength range.

        Args:
            minimum: Minimum wavelength.
            maximum: Maximum wavelength.
        """
        self._wavelength_range = (minimum, maximum)

    def set_flux_range(self, minimum: float, maximum: float) -> None:
        """Persist the flux range.

        Args:
            minimum: Minimum flux value.
            maximum: Maximum flux value.
        """
        self._flux_range = (minimum, maximum)

    def get_flux_range(self) -> tuple[float, float]:
        """Return the current flux range."""
        return self._flux_range

    def get_wavelength_range(self) -> tuple[float, float]:
        """Return the current wavelength range."""
        return self._wavelength_range

    def get_spectrum_data(
        self,
    ) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]] | None:
        """Return cached spectrum triples if available."""
        return self._spectrum

    def set_spectrum_data(
        self, wavelength: tuple[float, ...], flux: tuple[float, ...], error: tuple[float, ...]
    ) -> None:
        """Store mock spectrum data for range calculations.

        Args:
            wavelength: Sequence of wavelength samples.
            flux: Sequence of flux samples.
            error: Sequence of flux uncertainty samples.
        """
        self._spectrum = (wavelength, flux, error)

    def auto_scale_ranges(self) -> None:
        """Record that auto-scaling was requested."""
        self.auto_scale_ranges_called = True


class MockSpectrumView:
    """Minimal SpectrumView substitute for presenter tests."""

    def __init__(self) -> None:
        """Initialize mock view with optional attributes."""
        self.plot_host = None
        self.spectrum_plot = None
        self.spectrum_input_adapter = None


@dataclass(slots=True)
class StateRecordingPlotComponent:
    """Spectrum plot fake that records public range and display state."""

    wavelength_range: tuple[float, float] | None = None
    flux_range: tuple[float, float] | None = None
    plot_range: tuple[float, float, float, float] = (1000.0, 2000.0, -0.5, 0.5)
    auto_range_all_count: int = 0
    auto_range_result: tuple[float, float, float, float] | None = None
    auto_range_flux_count: int = 0
    updated_project: SpectroscopyProject | None = None

    def set_wavelength_range(self, minimum: float, maximum: float) -> None:
        """Store the requested wavelength range.

        Args:
            minimum: Minimum wavelength.
            maximum: Maximum wavelength.
        """
        self.wavelength_range = (minimum, maximum)

    def set_flux_range(self, minimum: float, maximum: float) -> None:
        """Store the requested flux range.

        Args:
            minimum: Minimum flux.
            maximum: Maximum flux.
        """
        self.flux_range = (minimum, maximum)

    def set_plot_range(
        self, minimum_wave: float, maximum_wave: float, minimum_flux: float, maximum_flux: float
    ) -> None:
        """Store a combined wavelength and flux range.

        Args:
            minimum_wave: Minimum wavelength.
            maximum_wave: Maximum wavelength.
            minimum_flux: Minimum flux.
            maximum_flux: Maximum flux.
        """
        self.plot_range = (minimum_wave, maximum_wave, minimum_flux, maximum_flux)
        self.wavelength_range = (minimum_wave, maximum_wave)
        self.flux_range = (minimum_flux, maximum_flux)

    def get_plot_range(self) -> tuple[float, float, float, float]:
        """Return the current plot range."""
        return self.plot_range

    def has_valid_renderer(self) -> bool:
        """Return whether the fake renderer can provide plot bounds."""
        return True

    def auto_range_all(self) -> None:
        """Record an auto-range request and settle the configured result."""
        self.auto_range_all_count += 1
        if self.auto_range_result is not None:
            self.plot_range = self.auto_range_result

    def auto_range_flux(self) -> None:
        """Record a flux-only auto-range request."""
        self.auto_range_flux_count += 1

    def update_from_project(self, project: SpectroscopyProject) -> None:
        """Record the project used for a display refresh.

        Args:
            project: Project passed by the presenter.
        """
        self.updated_project = project


@dataclass(slots=True)
class StateRecordingRangeComponent:
    """Range controls fake that records public range state."""

    wavelength_range: tuple[float, float] | None = None
    flux_range: tuple[float, float] | None = None
    wavelength_range_changed: MockSignal = field(default_factory=MockSignal)

    def set_wavelength_range(self, minimum: float, maximum: float) -> None:
        """Store the requested wavelength range.

        Args:
            minimum: Minimum wavelength.
            maximum: Maximum wavelength.
        """
        self.wavelength_range = (minimum, maximum)

    def set_flux_range(self, minimum: float, maximum: float) -> None:
        """Store the requested flux range.

        Args:
            minimum: Minimum flux.
            maximum: Maximum flux.
        """
        self.flux_range = (minimum, maximum)
