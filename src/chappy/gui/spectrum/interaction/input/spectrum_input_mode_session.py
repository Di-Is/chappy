"""Capability state for spectrum input interactions."""

from __future__ import annotations

from chappy.gui.spectrum.policy import SpectrumInputCapabilities

DEFAULT_INPUT_CAPABILITIES = SpectrumInputCapabilities(
    identify_velocity_shortcut_enabled=False,
    detail_velocity_shortcut_enabled=False,
    identify_click_enabled=False,
    optimize_shift_click_enabled=False,
    absorber_drag_enabled=False,
)


class SpectrumInputModeSession:
    """Store mode-derived input-side capabilities."""

    def __init__(self) -> None:
        """Initialize the capability session."""
        self._capabilities = DEFAULT_INPUT_CAPABILITIES

    def set_capabilities(self, capabilities: SpectrumInputCapabilities) -> None:
        """Set the current input capabilities."""
        self._capabilities = capabilities

    def identify_velocity_shortcut_enabled(self) -> bool:
        """Return whether the Identify velocity shortcut is enabled."""
        return self._capabilities.identify_velocity_shortcut_enabled

    def detail_velocity_shortcut_enabled(self) -> bool:
        """Return whether velocity shortcut should be routed to Region Detail."""
        return self._capabilities.detail_velocity_shortcut_enabled

    def identify_click_enabled(self) -> bool:
        """Return whether raw identify clicks should be routed to mode owner."""
        return self._capabilities.identify_click_enabled

    def optimize_shift_click_enabled(self) -> bool:
        """Return whether optimize shift-click should be routed to mode owner."""
        return self._capabilities.optimize_shift_click_enabled

    def absorber_drag_enabled(self) -> bool:
        """Return whether absorber drag can be started in the current mode."""
        return self._capabilities.absorber_drag_enabled
