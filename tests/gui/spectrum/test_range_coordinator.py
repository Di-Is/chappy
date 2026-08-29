"""Tests for spectrum range coordination."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from chappy.application.history import RangeHistoryCommand, RangeSnapshot
from chappy.gui.spectrum.range_coordinator import RangeCoordinator

from .fixtures.mock_spectrum_view import (
    MockSpectrumDataBridge,
    StateRecordingPlotComponent,
    StateRecordingRangeComponent,
)


@dataclass
class _HistoryRecorder:
    """History recorder fake that records range change calls."""

    pushed: list[tuple[RangeHistoryCommand, bool]] = field(default_factory=list)

    def record_range_change(
        self,
        old_wave_range: tuple[float, float],
        new_wave_range: tuple[float, float],
        old_flux_range: tuple[float, float] | None,
        new_flux_range: tuple[float, float] | None,
        source: str,
    ) -> None:
        """Record a range change call."""
        command = RangeHistoryCommand(
            before=RangeSnapshot(wavelength_range=old_wave_range, flux_range=old_flux_range),
            after=RangeSnapshot(wavelength_range=new_wave_range, flux_range=new_flux_range),
            qualifier=source,
        )
        coalesce = source in {"interactor", "intent"}
        self.pushed.append((command, coalesce))


@dataclass
class _RangeHarness:
    """Range coordinator test harness."""

    data_bridge: MockSpectrumDataBridge
    plot: StateRecordingPlotComponent
    range_input: StateRecordingRangeComponent
    history_recorder: _HistoryRecorder | None
    coordinator: RangeCoordinator


def _harness(
    *,
    history_recorder: _HistoryRecorder | None = None,
    flux_range_override: tuple[float, float] | None = None,
) -> _RangeHarness:
    """Create a range coordinator with state-recording collaborators."""
    data_bridge = MockSpectrumDataBridge()
    data_bridge.set_wavelength_range(1000.0, 2000.0)
    data_bridge.set_flux_range(-0.5, 0.5)
    plot = StateRecordingPlotComponent(plot_range=(1000.0, 2000.0, -0.5, 0.5))
    range_input = StateRecordingRangeComponent()
    coordinator = RangeCoordinator(
        data_bridge_provider=lambda: data_bridge,
        plot_host_provider=lambda: plot,
        range_input_provider=lambda: range_input,
        history_recorder_provider=lambda: history_recorder,
        flux_range_override_provider=lambda: flux_range_override,
    )
    return _RangeHarness(
        data_bridge=data_bridge,
        plot=plot,
        range_input=range_input,
        history_recorder=history_recorder,
        coordinator=coordinator,
    )


def test_coordinate_range_update_syncs_state_plot_and_inputs() -> None:
    """Range updates should synchronize the shared range surfaces."""
    harness = _harness()

    harness.coordinator.coordinate_range_update("manual", 3000.0, 5000.0)

    assert harness.data_bridge.get_wavelength_range() == (3000.0, 5000.0)
    assert harness.plot.wavelength_range == (3000.0, 5000.0)
    assert harness.range_input.wavelength_range == (3000.0, 5000.0)


def test_coordinate_range_update_syncs_flux_ranges() -> None:
    """Flux range updates should synchronize the plot and range controls."""
    harness = _harness()

    harness.coordinator.coordinate_range_update("manual", 3000.0, 5000.0, flux_range=(-0.25, 1.25))

    assert harness.data_bridge.get_flux_range() == (-0.25, 1.25)
    assert harness.plot.flux_range == (-0.25, 1.25)
    assert harness.range_input.flux_range == (-0.25, 1.25)


def test_coordinate_range_update_records_history_with_old_and_new_ranges() -> None:
    """History events should contain explicit before and after range snapshots."""
    history_recorder = _HistoryRecorder()
    harness = _harness(history_recorder=history_recorder)

    harness.coordinator.coordinate_range_update("intent", 1200.0, 1800.0, flux_range=(-0.2, 0.8))

    assert len(history_recorder.pushed) == 1
    command, coalesce = history_recorder.pushed[0]
    assert coalesce is True
    assert isinstance(command, RangeHistoryCommand)
    assert command.before.wavelength_range == (1000.0, 2000.0)
    assert command.before.flux_range == (-0.5, 0.5)
    assert command.after.wavelength_range == (1200.0, 1800.0)
    assert command.after.flux_range == (-0.2, 0.8)
    assert command.qualifier == "intent"


def test_coordinate_range_update_skips_history_without_bridge() -> None:
    """Missing history recorder should be a valid no-history path."""
    harness = _harness(history_recorder=None)

    harness.coordinator.coordinate_range_update("manual", 1200.0, 1800.0)

    assert harness.data_bridge.get_wavelength_range() == (1200.0, 1800.0)


def test_reset_view_ranges_auto_scales_when_no_bounds() -> None:
    """Reset without explicit bounds should auto-scale and synchronize final ranges."""
    harness = _harness()
    harness.plot.auto_range_result = (900.0, 2100.0, -0.3, 0.7)

    harness.coordinator.reset_view_ranges()

    assert harness.data_bridge.auto_scale_ranges_called
    assert harness.plot.auto_range_all_count == 1
    assert harness.data_bridge.get_wavelength_range() == (900.0, 2100.0)
    assert harness.data_bridge.get_flux_range() == (-0.3, 0.7)


def test_reset_view_ranges_applies_explicit_bounds() -> None:
    """Explicit reset bounds should update coordinated state without auto-scale."""
    harness = _harness()

    harness.coordinator.reset_view_ranges(
        wavelength_range=(1200.0, 2200.0), flux_range=(-0.2, 0.8)
    )

    assert harness.data_bridge.get_wavelength_range() == (1200.0, 2200.0)
    assert harness.data_bridge.get_flux_range() == (-0.2, 0.8)
    assert not harness.data_bridge.auto_scale_ranges_called
    assert harness.plot.plot_range == (1200.0, 2200.0, -0.2, 0.8)


def test_reset_view_ranges_without_flux_uses_plot_bounds() -> None:
    """Explicit reset without flux bounds should use current plot flux limits."""
    harness = _harness()
    harness.plot.plot_range = (1000.0, 2000.0, -0.3, 0.6)

    harness.coordinator.reset_view_ranges(wavelength_range=(1100.0, 1900.0))

    assert harness.data_bridge.get_wavelength_range() == (1100.0, 1900.0)
    assert harness.data_bridge.get_flux_range() == (-0.3, 0.6)
    assert not harness.data_bridge.auto_scale_ranges_called
    assert harness.plot.plot_range == (1100.0, 1900.0, -0.3, 0.6)


def test_auto_flux_range_requires_data_bridge() -> None:
    """Auto flux range calculation requires a data bridge dependency."""
    plot = StateRecordingPlotComponent()
    coordinator = RangeCoordinator(
        data_bridge_provider=lambda: None,
        plot_host_provider=lambda: plot,
        range_input_provider=lambda: None,
        history_recorder_provider=lambda: None,
        flux_range_override_provider=lambda: None,
    )

    with pytest.raises(RuntimeError, match="Data bridge is required"):
        coordinator.handle_auto_flux_range_request()


def test_auto_flux_range_without_spectrum_uses_plot_fallback() -> None:
    """No loaded spectrum should fall back to plot auto flux behavior."""
    harness = _harness()

    harness.coordinator.handle_auto_flux_range_request()

    assert harness.plot.auto_range_flux_count == 1


def test_auto_flux_range_prefers_override_range() -> None:
    """An available flux override should win over data-derived auto ranges."""
    harness = _harness(flux_range_override=(-0.15, 1.35))

    harness.coordinator.handle_auto_flux_range_request()

    assert harness.data_bridge.get_flux_range() == (-0.15, 1.35)
    assert harness.plot.flux_range == (-0.15, 1.35)
    assert harness.plot.auto_range_flux_count == 0
