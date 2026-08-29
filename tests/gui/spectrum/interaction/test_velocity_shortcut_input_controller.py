"""Tests for velocity shortcut input controller."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from chappy.gui.spectrum.interaction.input.controllers.velocity_shortcut_input_controller import (
    VelocityShortcutInputController,
)
from chappy.presentation.interaction.interaction_contracts import InteractionChannel


@dataclass
class _ModeCapabilitiesFake:
    """Mode capability fake for velocity shortcut tests."""

    identify_enabled: bool = False
    mode_enabled: bool = False

    def identify_velocity_shortcut_enabled(self) -> bool:
        """Return whether identify velocity shortcut is enabled."""
        return self.identify_enabled

    def detail_velocity_shortcut_enabled(self) -> bool:
        """Return whether mode velocity shortcut is enabled."""
        return self.mode_enabled


@dataclass
class _VelocityShortcutOwnerFake:
    """Owner fake for velocity shortcut tests."""

    active_channel: InteractionChannel | None = None
    pending: bool = False
    target_wavelength: float | None = 1215.67
    mode_shortcut_count: int = 0
    rect_zoom_cancel_reason: str | None = None
    velocity_cancel_reason: str | None = None
    entered_velocity: tuple[float | None, int | None, str] | None = None

    def active_input_channel(self) -> InteractionChannel | None:
        """Return the active channel."""
        return self.active_channel

    def cancel_rect_zoom_interaction(self, *, reason: str) -> bool:
        """Record rectangle zoom cancellation."""
        self.rect_zoom_cancel_reason = reason
        self.active_channel = None
        return True

    def is_velocity_pending(self) -> bool:
        """Return whether velocity is pending."""
        return self.pending

    def cancel_velocity_pending(self, *, reason: str) -> None:
        """Record velocity cancellation."""
        self.velocity_cancel_reason = reason
        self.pending = False

    def resolve_velocity_toggle_wavelength(self) -> float | None:
        """Return the configured target wavelength."""
        return self.target_wavelength

    def enter_velocity_pending(
        self, wavelength: float | None, modifiers: int | None, *, trigger: str
    ) -> None:
        """Record velocity pending entry."""
        self.entered_velocity = (wavelength, modifiers, trigger)
        self.pending = True

    def emit_mode_velocity_shortcut(self) -> None:
        """Record mode shortcut routing."""
        self.mode_shortcut_count += 1


def _controller(
    *, owner: _VelocityShortcutOwnerFake, capabilities: _ModeCapabilitiesFake
) -> VelocityShortcutInputController:
    """Create a controller with test dependencies."""
    return VelocityShortcutInputController(
        owner=owner, mode_capabilities=capabilities, logger=logging.getLogger(__name__)
    )


def test_mode_velocity_shortcut_routes_to_mode_owner() -> None:
    """Mode-owned velocity shortcuts should emit through the owner port."""
    owner = _VelocityShortcutOwnerFake()
    controller = _controller(owner=owner, capabilities=_ModeCapabilitiesFake(mode_enabled=True))

    assert controller.trigger_velocity_shortcut() is True
    assert owner.mode_shortcut_count == 1


def test_identify_velocity_shortcut_routes_to_identify_runtime() -> None:
    """Identify runtime chooses active-preview or pending behavior."""
    owner = _VelocityShortcutOwnerFake(target_wavelength=1400.0)
    controller = _controller(
        owner=owner, capabilities=_ModeCapabilitiesFake(identify_enabled=True)
    )

    assert controller.trigger_velocity_shortcut() is True
    assert owner.mode_shortcut_count == 1
    assert owner.entered_velocity is None


def test_identify_velocity_shortcut_cancels_rect_zoom_before_runtime_route() -> None:
    """Rectangle zoom is cancelled before Identify resolves preview or pending."""
    owner = _VelocityShortcutOwnerFake(active_channel=InteractionChannel.RECT_ZOOM)
    controller = _controller(
        owner=owner, capabilities=_ModeCapabilitiesFake(identify_enabled=True)
    )

    assert controller.trigger_velocity_shortcut() is True
    assert owner.rect_zoom_cancel_reason == "velocity-shortcut"
    assert owner.mode_shortcut_count == 1
    assert owner.entered_velocity is None


def test_velocity_shortcut_rejects_competing_channel() -> None:
    """Competing channels should block velocity shortcut handling."""
    owner = _VelocityShortcutOwnerFake(active_channel=InteractionChannel.MASK_SELECTION)
    controller = _controller(
        owner=owner, capabilities=_ModeCapabilitiesFake(identify_enabled=True)
    )

    assert controller.trigger_velocity_shortcut() is False
    assert owner.entered_velocity is None
    assert owner.velocity_cancel_reason is None


def test_velocity_shortcut_repress_cancels_pending() -> None:
    """Re-pressing identify velocity shortcut should cancel pending state."""
    owner = _VelocityShortcutOwnerFake(active_channel=InteractionChannel.VELOCITY, pending=True)
    controller = _controller(
        owner=owner, capabilities=_ModeCapabilitiesFake(identify_enabled=True)
    )

    assert controller.trigger_velocity_shortcut() is True
    assert owner.velocity_cancel_reason == "shortcut-toggle"
