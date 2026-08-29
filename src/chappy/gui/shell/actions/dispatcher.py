"""Dispatcher for typed shell actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QT_TRANSLATE_NOOP, QCoreApplication

from chappy.core.editing_mode import EditingMode
from chappy.gui.shell.actions.ids import ShellActionId

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.history.bridge import HistoryBridge
    from chappy.gui.shell.dependencies import (
        DialogCommandPort,
        ModeCommandPort,
        ProjectCommandPort,
        SpectrumNavigationPort,
        WindowChromePort,
    )
    from chappy.gui.spectrum.policy import SpectrumPolicy


UNDO_STATUS_SOURCE = str(QT_TRANSLATE_NOOP("MenuActionFactory", "Undone"))
REDO_STATUS_SOURCE = str(QT_TRANSLATE_NOOP("MenuActionFactory", "Redone"))
UNDO_REDO_FAILURE_SOURCE = str(
    QT_TRANSLATE_NOOP("MenuActionFactory", "Cannot undo/redo: {reason}")
)


class ActionDispatcher:
    """Dispatch shell action IDs to operation-specific command ports."""

    def __init__(  # noqa: PLR0913 - explicit shell command surfaces
        self,
        *,
        project_commands: ProjectCommandPort,
        mode_commands: ModeCommandPort,
        dialog_commands: DialogCommandPort,
        navigation_commands: SpectrumNavigationPort,
        window_commands: WindowChromePort,
        status_emitter: Callable[[str, int], None],
        tutorial_callback: Callable[[], None],
        about_callback: Callable[[], None],
        spectrum_policy_provider: Callable[[], SpectrumPolicy | None],
        fit_running_provider: Callable[[], bool],
    ) -> None:
        """Store action command ports and shell callbacks."""
        self._project_commands = project_commands
        self._mode_commands = mode_commands
        self._dialog_commands = dialog_commands
        self._navigation_commands = navigation_commands
        self._window_commands = window_commands
        self._status_emitter = status_emitter
        self._tutorial_callback = tutorial_callback
        self._about_callback = about_callback
        self._spectrum_policy_provider = spectrum_policy_provider
        self._fit_running_provider = fit_running_provider
        self._history_bridge: HistoryBridge | None = None

    def set_history_bridge(self, bridge: HistoryBridge) -> None:
        """Set the history bridge used for undo/redo dispatch."""
        self._history_bridge = bridge

    def dispatch(self, action_id: ShellActionId) -> None:
        """Dispatch a shell action.

        Args:
            action_id: Typed action identifier to execute.
        """
        if action_id is ShellActionId.OPEN_OBSERVATION_DATA:
            self._project_commands.open_observation_data()
        elif action_id is ShellActionId.OPEN_PROJECT:
            self._project_commands.open_project()
        elif action_id is ShellActionId.SAVE_PROJECT:
            self._project_commands.save_project()
        elif action_id is ShellActionId.SAVE_PROJECT_AS:
            self._project_commands.save_project_as()
        elif action_id is ShellActionId.CLOSE_PROJECT:
            self._project_commands.close_project()
        elif action_id is ShellActionId.QUIT:
            self._window_commands.close()
        elif action_id is ShellActionId.UNDO:
            self._dispatch_history_action(is_undo=True)
        elif action_id is ShellActionId.REDO:
            self._dispatch_history_action(is_undo=False)
        elif action_id is ShellActionId.DELETE:
            self._mode_commands.delete_selection()
        elif action_id is ShellActionId.ZOOM_IN:
            self._navigation_commands.zoom_in()
        elif action_id is ShellActionId.ZOOM_OUT:
            self._navigation_commands.zoom_out()
        elif action_id is ShellActionId.RESET_VIEW:
            self._navigation_commands.reset_view()
        elif action_id is ShellActionId.AUTO_ADJUST_FLUX:
            self._navigation_commands.auto_adjust_flux()
        elif action_id is ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY:
            if self._identify_velocity_allowed():
                self._navigation_commands.toggle_velocity_plot_identify()
        elif action_id is ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS:
            if not self._detail_velocity_allowed():
                return
            self._navigation_commands.toggle_velocity_plot_optimize()
        elif action_id is ShellActionId.FIT_MODEL:
            if not self._fit_allowed():
                return
            self._mode_commands.fit_model()
        elif action_id is ShellActionId.IDENTIFY_MODE:
            self._mode_commands.switch_mode(EditingMode.IDENTIFY)
        elif action_id is ShellActionId.ANALYSIS_MODE:
            self._mode_commands.switch_mode(EditingMode.ANALYSIS)
        elif action_id is ShellActionId.ANALYSIS_BACK:
            self._mode_commands.back_to_analysis_overview()
        elif action_id is ShellActionId.CONTINUUM_MODE:
            self._mode_commands.switch_mode(EditingMode.CONTINUUM)
        elif action_id is ShellActionId.OPEN_LINE_DATABASE_FOLDER:
            self._dialog_commands.open_line_database_folder()
        elif action_id is ShellActionId.COSMOLOGY_SETTINGS:
            self._dialog_commands.show_cosmology_dialog()
        elif action_id is ShellActionId.RESOLUTION_SETTINGS:
            self._dialog_commands.show_resolution_dialog()
        elif action_id is ShellActionId.LANGUAGE_SETTINGS:
            self._dialog_commands.show_language_dialog()
        elif action_id is ShellActionId.PRESET_MANAGEMENT:
            self._dialog_commands.show_preset_list_dialog()
        elif action_id is ShellActionId.HELP:
            self._dialog_commands.open_user_manual()
        elif action_id is ShellActionId.TUTORIAL:
            self._tutorial_callback()
        elif action_id is ShellActionId.ABOUT:
            self._about_callback()
        else:
            msg = f"Unsupported shell action: {action_id.value}"
            raise ValueError(msg)

    def _fit_allowed(self) -> bool:
        policy = self._spectrum_policy_provider()
        return (
            self._window_commands.current_project is not None
            and policy is not None
            and policy.fit_model_enabled
            and not self._fit_running_provider()
        )

    def _identify_velocity_allowed(self) -> bool:
        policy = self._spectrum_policy_provider()
        return bool(
            self._window_commands.current_project is not None
            and policy is not None
            and policy.input_capabilities.identify_velocity_shortcut_enabled
        )

    def _detail_velocity_allowed(self) -> bool:
        policy = self._spectrum_policy_provider()
        return bool(
            self._window_commands.current_project is not None
            and policy is not None
            and policy.input_capabilities.detail_velocity_shortcut_enabled
        )

    def _dispatch_history_action(self, *, is_undo: bool) -> None:
        """Dispatch undo/redo through the configured history bridge."""
        if self._history_bridge is None:
            msg = "History bridge is required for undo/redo actions."
            raise RuntimeError(msg)
        success, message = self._history_bridge.undo() if is_undo else self._history_bridge.redo()
        if success:
            source = UNDO_STATUS_SOURCE if is_undo else REDO_STATUS_SOURCE
            action_word = QCoreApplication.translate("MenuActionFactory", source)
            self._status_emitter(f"{action_word}: {message}", 2000)
        else:
            template = QCoreApplication.translate("MenuActionFactory", UNDO_REDO_FAILURE_SOURCE)
            self._status_emitter(template.format(reason=message), 3000)
