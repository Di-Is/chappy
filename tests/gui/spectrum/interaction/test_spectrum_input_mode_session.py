"""Tests for spectrum input capability state."""

from __future__ import annotations

from chappy.gui.spectrum.policy import SpectrumInputCapabilities
from chappy.gui.spectrum.interaction.input.spectrum_input_mode_session import (
    SpectrumInputModeSession,
)


def test_identify_capabilities_enable_identify_input_behavior() -> None:
    """Identify capabilities should enable identify click and velocity pending behavior."""
    session = SpectrumInputModeSession()
    capabilities = SpectrumInputCapabilities(
        identify_velocity_shortcut_enabled=True,
        detail_velocity_shortcut_enabled=False,
        identify_click_enabled=True,
        optimize_shift_click_enabled=False,
        absorber_drag_enabled=False,
    )

    session.set_capabilities(capabilities)

    assert session.identify_click_enabled() is True
    assert session.identify_velocity_shortcut_enabled() is True
    assert session.detail_velocity_shortcut_enabled() is False
    assert session.optimize_shift_click_enabled() is False
    assert session.absorber_drag_enabled() is False


def test_optimize_capabilities_enable_optimize_input_behavior() -> None:
    """Optimize capabilities should enable optimize-specific input behavior."""
    session = SpectrumInputModeSession()
    capabilities = SpectrumInputCapabilities(
        identify_velocity_shortcut_enabled=False,
        detail_velocity_shortcut_enabled=True,
        identify_click_enabled=False,
        optimize_shift_click_enabled=True,
        absorber_drag_enabled=True,
    )

    session.set_capabilities(capabilities)

    assert session.identify_click_enabled() is False
    assert session.identify_velocity_shortcut_enabled() is False
    assert session.detail_velocity_shortcut_enabled() is True
    assert session.optimize_shift_click_enabled() is True
    assert session.absorber_drag_enabled() is True
