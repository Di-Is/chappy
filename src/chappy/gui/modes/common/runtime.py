"""Common mode-runtime contracts for shared spectrum surface ownership."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chappy.gui.protocols.context_menu import (
        ContextMenuActionDescriptor,
        ContextMenuActionIntent,
    )
    from chappy.gui.protocols.intent_types import ShowContextMenuIntent
    from chappy.gui.protocols.spectrum_intents import IdentifyModeIntent


class ModeRuntime(Protocol):
    """Mode-local runtime contract used by shell-owned spectrum routing."""

    def handle_mode_click(self, wavelength: float, flux: float, modifiers: int) -> None:
        """Handle a shared spectrum click for the active mode."""

    def handle_mode_velocity_shortcut(self) -> None:
        """Handle a shared velocity shortcut for the active mode."""

    def handle_context_menu_intent(self, intent: ContextMenuActionIntent) -> None:
        """Handle a selected context-menu intent for the active mode."""

    def handle_identify_intent(self, intent: IdentifyModeIntent) -> None:
        """Handle an identify-mode intent routed through the active runtime."""

    def context_menu_actions(
        self, request: ShowContextMenuIntent
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Return context-menu actions for the active mode runtime."""


__all__ = ["ModeRuntime"]
