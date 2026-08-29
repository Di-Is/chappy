"""Optimize-mode handling for shared spectrum surface intents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.protocols.context_menu import (
        ContextMenuActionDescriptor,
        ContextMenuActionIntent,
    )
    from chappy.gui.protocols.intent_types import ShowContextMenuIntent
    from chappy.gui.protocols.spectrum_intents import IdentifyModeIntent


class OptimizeSharedSurfaceIntegrationPort(Protocol):
    """Optimize integration operations used by shared surface intents."""

    def handle_shift_click(self, wavelength: float, flux: float) -> bool:
        """Handle an optimize shift-click."""
        ...

    def handle_velocity_shortcut(self) -> None:
        """Handle an optimize velocity shortcut."""
        ...

    def handle_context_menu_intent(self, intent: ContextMenuActionIntent) -> None:
        """Handle an optimize context menu intent."""
        ...


class OptimizeSharedSurfaceController:
    """Route shared spectrum surface actions to optimize-mode workflow."""

    def __init__(
        self,
        *,
        integration_provider: Callable[[], OptimizeSharedSurfaceIntegrationPort | None],
        spectrum_update_callback: Callable[[], None],
        context_menu_action_provider: (
            Callable[[float], tuple[ContextMenuActionDescriptor, ...]] | None
        ) = None,
    ) -> None:
        """Initialize the controller."""
        self._integration_provider = integration_provider
        self._spectrum_update_callback = spectrum_update_callback
        self._context_menu_action_provider = context_menu_action_provider

    def handle_mode_click(self, wavelength: float, flux: float, modifiers: int) -> None:
        """Handle a mode-specific spectrum click."""
        _ = modifiers
        integration = self._required_integration("optimize spectrum clicks")
        handled = integration.handle_shift_click(wavelength, flux)
        if handled:
            self._spectrum_update_callback()

    def handle_click(self, wavelength: float, flux: float) -> None:
        """Backward-compatible alias for optimize click handling."""
        self.handle_mode_click(wavelength, flux, 0)

    def handle_mode_velocity_shortcut(self) -> None:
        """Handle an optimize velocity shortcut."""
        self._required_integration("optimize velocity shortcuts").handle_velocity_shortcut()

    def handle_velocity_shortcut(self) -> None:
        """Backward-compatible alias for optimize velocity shortcuts."""
        self.handle_mode_velocity_shortcut()

    def handle_context_menu_intent(self, intent: ContextMenuActionIntent) -> None:
        """Handle an optimize context menu intent."""
        self._required_integration("optimize context menu intents").handle_context_menu_intent(
            intent
        )

    def handle_identify_intent(self, intent: IdentifyModeIntent) -> None:
        """Ignore identify-only intents for the optimize runtime."""
        _ = intent

    def context_menu_actions(
        self, request: ShowContextMenuIntent
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Return optimize context-menu actions for the active integration."""
        if self._context_menu_action_provider is None:
            return ()
        return self._context_menu_action_provider(float(request.wavelength))

    def _required_integration(self, purpose: str) -> OptimizeSharedSurfaceIntegrationPort:
        """Return optimize integration or raise for a missing owner."""
        integration = self._integration_provider()
        if integration is None:
            msg = f"Optimize integration is required for {purpose}."
            raise RuntimeError(msg)
        return integration
