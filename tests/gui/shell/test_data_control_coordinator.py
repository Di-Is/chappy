"""Tests for shared DataControlPanel coordination."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from chappy.gui.shell.data_control_coordinator import (
    DataControlCoordinator,
    DataControlCoordinatorPorts,
)


class _StubSignal:
    """Minimal signal stub compatible with the coordinator."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[..., None]] = []

    def connect(self, callback: Callable[..., None]) -> None:
        """Register a callback."""
        self._callbacks.append(callback)

    def emit(self, *args: object) -> None:
        """Call registered callbacks."""
        for callback in list(self._callbacks):
            callback(*args)


@dataclass
class _RangeValuesSnapshot:
    """Snapshot of range values received by the panel fake."""

    wavelength_min: float
    wavelength_max: float
    flux_min: float
    flux_max: float


class _FakePanel:
    """Panel fake exposing the shared signal and setter surface."""

    def __init__(self) -> None:
        self.wavelength_range_applied = _StubSignal()
        self.flux_range_applied = _StubSignal()
        self.reset_requested = _StubSignal()
        self.auto_adjust_requested = _StubSignal()
        self.range_updates: list[_RangeValuesSnapshot] = []
        self.wavelength_enabled: list[bool] = []

    def update_ranges(self, values: object) -> None:
        """Record range updates."""
        self.range_updates.append(
            _RangeValuesSnapshot(
                wavelength_min=values.wavelength_min,
                wavelength_max=values.wavelength_max,
                flux_min=values.flux_min,
                flux_max=values.flux_max,
            )
        )

    def set_wavelength_fields_enabled(self, enabled: bool) -> None:
        """Record wavelength-field availability changes."""
        self.wavelength_enabled.append(enabled)


class _FakeSpectrumCoordinator:
    """Spectrum coordinator fake used by DataControlCoordinator tests."""

    def __init__(self) -> None:
        self.coordinate_calls: list[tuple[str, float, float, tuple[float, float] | None]] = []
        self.reset_calls: list[tuple[tuple[float, float] | None, tuple[float, float] | None]] = []
        self.auto_adjust_calls = 0

    def coordinate_range_update(
        self,
        *,
        source: str,
        min_wave: float,
        max_wave: float,
        flux_range: tuple[float, float] | None = None,
    ) -> None:
        """Record coordinated range updates."""
        self.coordinate_calls.append((source, min_wave, max_wave, flux_range))

    def reset_view_ranges(
        self,
        *,
        wavelength_range: tuple[float, float] | None = None,
        flux_range: tuple[float, float] | None = None,
    ) -> None:
        """Record reset requests."""
        self.reset_calls.append((wavelength_range, flux_range))

    def handle_auto_flux_range_request(self) -> None:
        """Record auto-flux requests."""
        self.auto_adjust_calls += 1


class _FakeSpectrumView:
    """Spectrum view fake exposing the shared surface callbacks."""

    def __init__(self) -> None:
        self.coordinator = _FakeSpectrumCoordinator()
        self.range_changed = _StubSignal()
        self._wavelength_callback = None
        self._wavelength_range = (4100.0, 4200.0)
        self._reset_ranges = ((4050.0, 4250.0), (-0.25, 1.5))

    def set_wavelength_fields_enabled_callback(self, callback: Callable[[bool], None]) -> None:
        """Store the wavelength-field callback."""
        self._wavelength_callback = callback

    def get_wavelength_range(self) -> tuple[float, float]:
        """Return the current wavelength range."""
        return self._wavelength_range

    def get_reset_ranges(self) -> tuple[tuple[float, float], tuple[float, float] | None] | None:
        """Return the stored reset payload."""
        return self._reset_ranges


def test_data_control_coordinator_routes_panel_and_spectrum_updates() -> None:
    """Shared panel requests should route through the coordinator boundary."""
    panel = _FakePanel()
    spectrum_view = _FakeSpectrumView()
    statuses: list[tuple[str, int]] = []

    coordinator = DataControlCoordinator(
        DataControlCoordinatorPorts(
            panel=panel,
            spectrum_view_provider=lambda: spectrum_view,
            status_message=lambda message, timeout_ms: statuses.append((message, timeout_ms)),
        )
    )

    coordinator.connect_signals()

    panel.wavelength_range_applied.emit(4300.0, 4400.0)
    panel.flux_range_applied.emit(-0.1, 1.2)
    panel.reset_requested.emit()
    panel.auto_adjust_requested.emit()
    spectrum_view.range_changed.emit(4000.0, 4500.0, -0.2, 1.4)
    spectrum_view._wavelength_callback(False)

    assert spectrum_view.coordinator.coordinate_calls == [
        ("manual", 4300.0, 4400.0, None),
        ("manual", 4100.0, 4200.0, (-0.1, 1.2)),
    ]
    assert spectrum_view.coordinator.reset_calls == [((4050.0, 4250.0), (-0.25, 1.5))]
    assert spectrum_view.coordinator.auto_adjust_calls == 1
    assert panel.range_updates == [_RangeValuesSnapshot(4000.0, 4500.0, -0.2, 1.4)]
    assert panel.wavelength_enabled == [False]
    assert statuses == [("Reset plot ranges", 1500), ("Auto-adjusted flux axis", 1500)]
