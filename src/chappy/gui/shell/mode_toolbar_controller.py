"""Own mode-context-bar state and toolbar intent dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.gui.shell.actions.ids import ShellActionId

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from PySide6.QtGui import QAction

    from chappy.core.editing_mode import EditingMode
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.shell.mode_context_bar import ModeContextBar, ModeContextConfig


class ModeToolbarController:
    """Connect toolbar intents and context-bar state for shell modes."""

    def __init__(
        self,
        *,
        action_map_provider: Callable[[], Mapping[ShellActionId, QAction]],
        zoom_rect_toggle_callback: Callable[[bool], None],
    ) -> None:
        """Store toolbar dependencies."""
        self._action_map_provider = action_map_provider
        self._zoom_rect_toggle_callback = zoom_rect_toggle_callback
        self._context_bar: ModeContextBar | None = None
        self._zoom_button_checked = False

    def bind_context_bar(self, context_bar: ModeContextBar | None) -> None:
        """Bind the current context bar and connect its signals."""
        if context_bar is None or context_bar is self._context_bar:
            return

        self._context_bar = context_bar
        context_bar.toolbar_action_triggered.connect(self.handle_toolbar_action)
        context_bar.zoom_rect_toggled.connect(self._zoom_rect_toggle_callback)
        context_bar.mode_switch_requested.connect(self.handle_mode_switch_request)
        self.set_zoom_button_checked(self._zoom_button_checked)

    @property
    def has_bound_context_bar(self) -> bool:
        """Return whether a context bar is currently bound."""
        return self._context_bar is not None

    def set_zoom_button_checked(self, checked: bool) -> None:
        """Synchronize the zoom button checked state."""
        self._zoom_button_checked = checked
        if self._context_bar is not None:
            self._context_bar.set_zoom_mode_active(checked)

    def apply_mode(
        self,
        *,
        mode: EditingMode,
        config: ModeContextConfig | None,
        current_project: SpectroscopyProject | None,
    ) -> None:
        """Apply mode-specific state to the bound context bar."""
        context_bar = self._context_bar
        if context_bar is None or config is None:
            return

        context_bar.apply_config(config)
        context_bar.set_current_mode(mode)
        context_bar.set_project_loaded(current_project is not None)

    def handle_toolbar_action(self, action_id: object) -> None:
        """Handle toolbar actions emitted by the context bar."""
        if not isinstance(action_id, ShellActionId):
            msg = f"Unknown toolbar action: {action_id}"
            raise TypeError(msg)
        self.trigger_shell_action(action_id)

    def handle_mode_switch_request(self, action_id: object) -> None:
        """Handle mode-switch requests emitted by the context bar."""
        mode_actions = {
            ShellActionId.IDENTIFY_MODE,
            ShellActionId.ANALYSIS_MODE,
            ShellActionId.CONTINUUM_MODE,
        }
        if not isinstance(action_id, ShellActionId) or action_id not in mode_actions:
            msg = f"Unknown mode requested: {action_id}"
            raise ValueError(msg)
        self.trigger_shell_action(action_id)

    def trigger_shell_action(self, action_id: ShellActionId) -> None:
        """Trigger a registered shell action."""
        action = self._action_map_provider().get(action_id)
        if action is None:
            msg = f"Toolbar action is not registered: {action_id.value}"
            raise RuntimeError(msg)
        action.trigger()


__all__ = ["ModeToolbarController"]
