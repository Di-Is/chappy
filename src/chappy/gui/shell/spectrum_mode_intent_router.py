"""Shell-owned routing for mode-specific spectrum intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.gui.protocols.spectrum_intents import SpectrumModeIntentSink

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.modes.common import ModeRuntime
    from chappy.gui.protocols.context_menu import (
        ContextMenuActionDescriptor,
        ContextMenuActionIntent,
    )
    from chappy.gui.protocols.intent_types import ShowContextMenuIntent
    from chappy.gui.protocols.spectrum_intents import IdentifyModeIntent


@dataclass(frozen=True, slots=True)
class SpectrumModeIntentRouterPorts:
    """Providers required by the shell mode intent router."""

    active_runtime_provider: Callable[[], ModeRuntime | None]


class SpectrumModeIntentRouter(SpectrumModeIntentSink):
    """Route shared spectrum intents to the active mode runtime."""

    def __init__(self, ports: SpectrumModeIntentRouterPorts) -> None:
        """Initialize the router with shell-owned providers."""
        self._ports = ports

    def handle_mode_click(self, wavelength: float, flux: float, modifiers: int) -> None:
        """Route a raw spectrum click to the active mode runtime."""
        runtime = self._ports.active_runtime_provider()
        if runtime is None:
            return
        runtime.handle_mode_click(wavelength, flux, modifiers)

    def handle_mode_velocity_shortcut(self) -> None:
        """Route a raw velocity shortcut to the active mode runtime."""
        runtime = self._ports.active_runtime_provider()
        if runtime is None:
            return
        runtime.handle_mode_velocity_shortcut()

    def handle_context_menu_intent(self, intent: ContextMenuActionIntent) -> None:
        """Route a selected context-menu intent to the active mode runtime."""
        runtime = self._require_active_runtime("context menu intents")
        runtime.handle_context_menu_intent(intent)

    def handle_continuum_intent(self, intent: ContextMenuActionIntent) -> None:
        """Route a continuum-mode intent to the active mode runtime."""
        self.handle_context_menu_intent(intent)

    def handle_identify_intent(self, intent: IdentifyModeIntent) -> None:
        """Route an identify-mode intent to the active mode runtime."""
        runtime = self._require_active_runtime("identify intents")
        runtime.handle_identify_intent(intent)

    def context_menu_actions(
        self, request: ShowContextMenuIntent
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Return context-menu actions from the active mode runtime."""
        runtime = self._ports.active_runtime_provider()
        if runtime is None:
            return ()
        return runtime.context_menu_actions(request)

    def _require_active_runtime(self, purpose: str) -> ModeRuntime:
        """Return the active runtime or fail fast."""
        runtime = self._ports.active_runtime_provider()
        if runtime is None:
            msg = f"Active mode runtime is required for {purpose}."
            raise RuntimeError(msg)
        return runtime
