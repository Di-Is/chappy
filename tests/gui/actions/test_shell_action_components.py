"""Tests for typed shell action support components."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow

from chappy.core.editing_mode import EditingMode
from chappy.core.history.history_event import HistoryState
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.contracts import SpectrumProfile
from chappy.gui.shell.analysis_surface_ui_adapter import analysis_spectrum_policy
from chappy.gui.shell.actions import (
    ACTION_SOURCES,
    DEFAULT_ACTION_REGISTRY,
    MENU_SOURCES,
    ActionStateController,
    MenuBarBuilder,
)
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy
from chappy.gui.shell.actions.ids import ShellActionId


def test_default_action_registry_exposes_menu_and_action_sources() -> None:
    """The default registry should publish stable sources for menus and actions."""
    assert DEFAULT_ACTION_REGISTRY.actions
    assert DEFAULT_ACTION_REGISTRY.menus
    assert ACTION_SOURCES[ShellActionId.OPEN_PROJECT].text == "&Open Project..."
    assert MENU_SOURCES["file"].title == "&File"


def test_menu_bar_builder_builds_registered_menus(qtbot) -> None:
    """MenuBarBuilder should build menus from registry definitions."""
    window = QMainWindow()
    qtbot.addWidget(window)
    actions = {
        definition.action_id: QAction(definition.source.text, window)
        for definition in DEFAULT_ACTION_REGISTRY.actions
    }

    menubar, menus = MenuBarBuilder(
        main_window=window,
        menus=DEFAULT_ACTION_REGISTRY.menus,
        actions=actions,
        translator=lambda source_text: source_text,
    ).build()

    assert menubar.actions()
    assert set(menus) == {"file", "edit", "view", "mode", "settings", "help"}
    assert (
        menus["file"].actions()[0].text() == "&Open Project..."
        or menus["file"].actions()[0].text() == "Open Observation Data..."
    )
    assert any(action.isSeparator() for action in menus["file"].actions())


def test_action_state_controller_updates_history_project_and_mode_state(qtbot) -> None:
    """ActionStateController should synchronize QAction state from shell state."""
    window = QMainWindow()
    qtbot.addWidget(window)
    actions = {
        action_id: QAction(action_id.value, window)
        for action_id in (
            ShellActionId.UNDO,
            ShellActionId.REDO,
            ShellActionId.SAVE_PROJECT,
            ShellActionId.SAVE_PROJECT_AS,
            ShellActionId.CLOSE_PROJECT,
            ShellActionId.FIT_MODEL,
            ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY,
            ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS,
            ShellActionId.ZOOM_IN,
            ShellActionId.ZOOM_OUT,
            ShellActionId.RESET_VIEW,
            ShellActionId.AUTO_ADJUST_FLUX,
            ShellActionId.ANALYSIS_MODE,
            ShellActionId.IDENTIFY_MODE,
            ShellActionId.ANALYSIS_MODE,
            ShellActionId.CONTINUUM_MODE,
        )
    }
    for action_id in (
        ShellActionId.ANALYSIS_MODE,
        ShellActionId.IDENTIFY_MODE,
        ShellActionId.ANALYSIS_MODE,
        ShellActionId.CONTINUUM_MODE,
    ):
        actions[action_id].setCheckable(True)

    controller = ActionStateController(actions)

    controller.sync_history_state(
        HistoryState(
            can_undo=True,
            can_redo=False,
            undo_count=1,
            redo_count=0,
            next_undo_operation_id=None,
            next_redo_operation_id=None,
        )
    )
    assert actions[ShellActionId.UNDO].isEnabled() is True
    assert actions[ShellActionId.REDO].isEnabled() is False

    controller.sync_project_state(SpectroscopyProject())
    assert actions[ShellActionId.SAVE_PROJECT].isEnabled() is True
    assert actions[ShellActionId.FIT_MODEL].isEnabled() is False

    controller.sync_spectrum_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL))
    assert actions[ShellActionId.FIT_MODEL].isEnabled() is True
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS].isEnabled() is True
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS].isVisible() is True
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY].isEnabled() is False
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY].isVisible() is False
    controller.sync_spectrum_policy(spectrum_interaction_mode_policy(EditingMode.IDENTIFY))
    assert actions[ShellActionId.FIT_MODEL].isEnabled() is False
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS].isEnabled() is False
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS].isVisible() is False
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY].isEnabled() is True
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY].isVisible() is True

    controller.set_fit_running(True)
    controller.sync_spectrum_policy(analysis_spectrum_policy(SpectrumProfile.REGION_DETAIL))
    assert actions[ShellActionId.FIT_MODEL].isEnabled() is False
    controller.set_fit_running(False)
    assert actions[ShellActionId.FIT_MODEL].isEnabled() is True

    controller.clear_spectrum_policy()
    assert actions[ShellActionId.FIT_MODEL].isEnabled() is False
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_ANALYSIS].isVisible() is False
    assert actions[ShellActionId.TOGGLE_VELOCITY_PLOT_IDENTIFY].isVisible() is False

    controller.sync_mode_state(EditingMode.IDENTIFY)
    assert actions[ShellActionId.IDENTIFY_MODE].isChecked() is True
    assert actions[ShellActionId.ANALYSIS_MODE].isChecked() is False

    controller.set_mode_actions_enabled(False)
    assert actions[ShellActionId.CONTINUUM_MODE].isEnabled() is False
