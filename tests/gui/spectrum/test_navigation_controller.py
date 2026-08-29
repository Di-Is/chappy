"""Tests for spectrum navigation controller contracts."""

from __future__ import annotations

import pytest

from chappy.application.spectrum.range_usecase import RangeNavigationUseCase
from chappy.gui.protocols.intent_types import PanIntent, SelectRangeIntent, ZoomRectIntent
from chappy.gui.spectrum.navigation_controller import SpectrumNavigationController
from chappy.presentation.interaction.interaction_contracts import InteractionChannel


class _NavigationRecorder:
    """Record navigation side effects."""

    def __init__(self) -> None:
        self.range_updates: list[tuple[str, float, float, tuple[float, float] | None]] = []
        self.disable_auto_adjust_y_count = 0
        self.mode_commands: list[str] = []
        self.active_channel: InteractionChannel | None = None

    def coordinate_range_update(
        self,
        source: str,
        min_wave: float,
        max_wave: float,
        *,
        flux_range: tuple[float, float] | None = None,
    ) -> None:
        """Record a coordinated range update."""
        self.range_updates.append((source, min_wave, max_wave, flux_range))

    def disable_auto_adjust_y(self) -> None:
        """Record that automatic Y adjustment was disabled."""
        self.disable_auto_adjust_y_count += 1

    def emit_mode_command(self, command: str) -> None:
        """Record a requested mode command."""
        self.mode_commands.append(command)

    def active_interaction_channel(self) -> InteractionChannel | None:
        """Return the configured active interaction channel."""
        return self.active_channel


def _controller(
    recorder: _NavigationRecorder,
    *,
    current_range: tuple[float, float] | None = (1000.0, 2000.0),
    data_bounds: tuple[float, float] | None = (900.0, 2500.0),
) -> SpectrumNavigationController:
    """Create a navigation controller with recording dependencies."""
    return SpectrumNavigationController(
        current_range_provider=lambda: current_range,
        data_bounds_provider=lambda: data_bounds,
        coordinate_range_update=recorder.coordinate_range_update,
        disable_auto_adjust_y=recorder.disable_auto_adjust_y,
        active_interaction_channel_provider=recorder.active_interaction_channel,
        mode_command_emitter=recorder.emit_mode_command,
        range_usecase=RangeNavigationUseCase(),
    )


def test_navigation_without_current_range_is_user_state_skip() -> None:
    """No loaded spectrum should skip navigation without touching collaborators."""
    recorder = _NavigationRecorder()
    controller = _controller(recorder, current_range=None)

    controller.handle_navigation_intent(PanIntent(fraction=0.1))

    assert recorder.range_updates == []
    assert recorder.disable_auto_adjust_y_count == 0
    assert recorder.mode_commands == []


def test_pan_navigation_updates_range_from_controller() -> None:
    """Pan intents should be calculated and dispatched by the controller."""
    recorder = _NavigationRecorder()
    controller = _controller(recorder)

    controller.handle_navigation_intent(PanIntent(fraction=0.1))

    assert recorder.range_updates == [("intent", 1100.0, 2100.0, None)]
    assert recorder.disable_auto_adjust_y_count == 0
    assert recorder.mode_commands == []


def test_select_range_navigation_updates_range_from_controller() -> None:
    """Range selection should share the controller navigation path."""
    recorder = _NavigationRecorder()
    controller = _controller(recorder)

    controller.handle_navigation_intent(
        SelectRangeIntent(start_wavelength=1210.0, end_wavelength=1230.0)
    )

    assert recorder.range_updates == [("intent", 1210.0, 1230.0, None)]


def test_rect_zoom_disables_auto_y_and_requests_teardown_when_active() -> None:
    """Rectangle zoom should forward flux limits and clear active rect zoom mode."""
    recorder = _NavigationRecorder()
    recorder.active_channel = InteractionChannel.RECT_ZOOM
    controller = _controller(recorder)

    controller.handle_navigation_intent(
        ZoomRectIntent(min_wavelength=1200.0, max_wavelength=1300.0, min_flux=-0.2, max_flux=1.2)
    )

    assert recorder.range_updates == [("rect_zoom", 1200.0, 1300.0, (-0.2, 1.2))]
    assert recorder.disable_auto_adjust_y_count == 1
    assert recorder.mode_commands == ["disable_rect_zoom"]


def test_invalid_current_range_propagates_usecase_failure() -> None:
    """Invalid loaded range is a fail-fast invariant violation."""
    recorder = _NavigationRecorder()
    controller = _controller(recorder, current_range=(2000.0, 1000.0))

    with pytest.raises(ValueError, match="current_range must satisfy min < max"):
        controller.handle_navigation_intent(PanIntent(fraction=0.1))

    assert recorder.range_updates == []
