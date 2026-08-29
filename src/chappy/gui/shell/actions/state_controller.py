"""Action state synchronization helpers for the shell."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.core.editing_mode import EditingMode
from chappy.gui.shell.actions.ids import ShellActionId

if TYPE_CHECKING:
    from PySide6.QtGui import QAction

    from chappy.core.history import HistoryState
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.spectrum.policy import SpectrumPolicy


class ActionStateController:
    """Synchronize QAction state from project, mode, and history state."""

    def __init__(self, actions: dict[ShellActionId, QAction]) -> None:
        """Store the action map controlled by this state controller."""
        self._actions = actions
        self._has_project = False
        self._current_mode = EditingMode.START
        self._fit_model_capability = False
        self._fit_running = False
        self._identify_velocity_capability = False
        self._detail_velocity_capability = False

    def sync_history_state(self, state: HistoryState) -> None:
        """Update undo and redo availability from history state."""
        self._set_enabled(ShellActionId.UNDO, state.can_undo)
        self._set_enabled(ShellActionId.REDO, state.can_redo)

    def sync_project_state(self, project: SpectroscopyProject | None) -> None:
        """Update project-dependent action state."""
        has_project = project is not None
        self._has_project = has_project
        for action_id in (
            ShellActionId.SAVE_PROJECT,
            ShellActionId.SAVE_PROJECT_AS,
            ShellActionId.CLOSE_PROJECT,
            ShellActionId.ZOOM_IN,
            ShellActionId.ZOOM_OUT,
            ShellActionId.RESET_VIEW,
            ShellActionId.AUTO_ADJUST_FLUX,
        ):
            self._set_enabled(action_id, has_project)
        self._sync_fit_model_state()
        self._sync_velocity_action_state()
        self._sync_delete_state()

    def sync_spectrum_policy(self, policy: SpectrumPolicy) -> None:
        """Update spectrum-owned global capabilities from the applied policy."""
        self._fit_model_capability = policy.fit_model_enabled
        self._identify_velocity_capability = (
            policy.input_capabilities.identify_velocity_shortcut_enabled
        )
        self._detail_velocity_capability = (
            policy.input_capabilities.detail_velocity_shortcut_enabled
        )
        self._sync_fit_model_state()
        self._sync_velocity_action_state()

    def clear_spectrum_policy(self) -> None:
        """Disable scientific commands while spectrum policy state is unknown."""
        self._fit_model_capability = False
        self._identify_velocity_capability = False
        self._detail_velocity_capability = False
        self._sync_fit_model_state()
        self._sync_velocity_action_state()

    def _sync_fit_model_state(self) -> None:
        """Enable F5 only when both project and spectrum policy allow fitting."""
        self._set_enabled(
            ShellActionId.FIT_MODEL,
            self._has_project and self._fit_model_capability and not self._fit_running,
        )

    def set_fit_running(self, running: bool) -> None:
        """Keep fit busy state orthogonal to the active spectrum policy."""
        self._fit_running = running
        self._sync_fit_model_state()

    def _sync_velocity_action_state(self) -> None:
        """Expose exactly the velocity command allowed by the current policy."""
        self._set_capability_action(
            ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY, self._identify_velocity_capability
        )
        self._set_capability_action(
            ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS, self._detail_velocity_capability
        )

    def _set_capability_action(self, action_id: ShellActionId, allowed: bool) -> None:
        action = self._actions.get(action_id)
        if action is None:
            return
        enabled = self._has_project and allowed
        action.setVisible(enabled)
        action.setEnabled(enabled)
        if not enabled and action.isCheckable():
            action.setChecked(False)

    def sync_mode_state(self, current_mode: EditingMode) -> None:
        """Update checked state for mode-selection actions."""
        self._current_mode = current_mode
        self._set_checked(ShellActionId.IDENTIFY_MODE, current_mode == EditingMode.IDENTIFY)
        self._set_checked(ShellActionId.ANALYSIS_MODE, current_mode == EditingMode.ANALYSIS)
        self._set_checked(ShellActionId.CONTINUUM_MODE, current_mode == EditingMode.CONTINUUM)
        self._sync_delete_state()

    def _sync_delete_state(self) -> None:
        """Leave Delete disabled until a surface policy grants Structure scope."""
        self._set_enabled(ShellActionId.DELETE, False)

    def set_mode_actions_enabled(self, enabled: bool) -> None:
        """Enable or disable mode-switching actions."""
        for action_id in (
            ShellActionId.IDENTIFY_MODE,
            ShellActionId.ANALYSIS_MODE,
            ShellActionId.CONTINUUM_MODE,
        ):
            self._set_enabled(action_id, enabled)

    def _set_enabled(self, action_id: ShellActionId, enabled: bool) -> None:
        """Set enabled state when the action exists."""
        action = self._actions.get(action_id)
        if action is not None:
            action.setEnabled(enabled)

    def _set_checked(self, action_id: ShellActionId, checked: bool) -> None:
        """Set checked state when the action exists."""
        action = self._actions.get(action_id)
        if action is not None:
            action.setChecked(checked)
