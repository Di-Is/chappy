"""Continuum-mode handling for shared spectrum surface intents."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.gui.modes.continuum import ContinuumContextMenuController, ContinuumContextMenuRequest
from chappy.gui.protocols.intent_types import AddContinuumPointIntent, DeleteContinuumPointIntent

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.protocols.context_menu import (
        ContextMenuActionDescriptor,
        ContextMenuActionIntent,
    )
    from chappy.gui.protocols.intent_types import ShowContextMenuIntent
    from chappy.gui.protocols.spectrum_intents import IdentifyModeIntent
    from chappy.plotting.components.continuum_editor import ContinuumContextState


class ContinuumSharedSurfaceEditorPort(Protocol):
    """Continuum editor operations used by shared surface intents."""

    def get_context_state(self, wavelength: float, flux: float | None) -> ContinuumContextState:
        """Return context menu availability at the requested coordinates."""
        ...

    def request_add_point(self, wavelength: float, flux: float) -> None:
        """Request a new continuum control point."""
        ...

    def request_delete_point(self, index: int) -> None:
        """Request deletion of a continuum control point."""
        ...


class ContinuumSharedSurfaceContextController:
    """Route shared spectrum surface actions to continuum-mode workflow."""

    def __init__(
        self,
        *,
        editor_provider: Callable[[], ContinuumSharedSurfaceEditorPort | None],
        add_continuum_callback: Callable[[], None] | None = None,
        action_provider: ContinuumContextMenuController | None = None,
    ) -> None:
        """Initialize the controller."""
        self._editor_provider = editor_provider
        self._add_continuum_callback = add_continuum_callback
        self._action_provider = action_provider or ContinuumContextMenuController()

    def handle_mode_click(self, wavelength: float, flux: float, modifiers: int) -> None:
        """Continuum runtime ignores shared spectrum clicks."""
        _ = wavelength, flux, modifiers

    def handle_mode_velocity_shortcut(self) -> None:
        """Continuum runtime ignores shared velocity shortcuts."""
        return

    def handle_context_menu_intent(self, intent: ContextMenuActionIntent) -> None:
        """Handle a continuum context menu intent."""
        if not isinstance(intent, (AddContinuumPointIntent, DeleteContinuumPointIntent)):
            return

        editor = self._required_editor()
        if isinstance(intent, AddContinuumPointIntent):
            editor.request_add_point(intent.wavelength, intent.flux)
            return

        editor.request_delete_point(intent.index)

    def handle_identify_intent(self, intent: IdentifyModeIntent) -> None:
        """Ignore identify-only intents for the continuum runtime."""
        _ = intent

    def add_continuum(self) -> None:
        """Add a continuum component through the continuum-mode owner."""
        if self._add_continuum_callback is None:
            msg = "Continuum add command is required for continuum runtime commands."
            raise RuntimeError(msg)
        self._add_continuum_callback()

    def context_menu_actions(
        self, intent: ShowContextMenuIntent
    ) -> tuple[ContextMenuActionDescriptor, ...]:
        """Return continuum context-menu actions for the active editor."""
        editor = self._required_editor()
        state = editor.get_context_state(float(intent.wavelength), intent.flux)
        return self._action_provider.actions_for_request(
            ContinuumContextMenuRequest(
                wavelength=float(intent.wavelength),
                flux=intent.flux,
                can_add=bool(state.can_add),
                can_delete=bool(state.can_delete),
                nearest_index=state.nearest_index,
            )
        )

    def _required_editor(self) -> ContinuumSharedSurfaceEditorPort:
        """Return continuum editor or raise for a missing owner."""
        editor = self._editor_provider()
        if editor is None:
            msg = "Continuum editor is required for continuum context menu intents."
            raise RuntimeError(msg)
        return editor
