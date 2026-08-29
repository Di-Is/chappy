"""Tests for the shell Display menu toggle controller."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow
from pytestqt.qtbot import QtBot

from chappy.gui.shell.data_control_panel import DataControlPanel
from chappy.gui.shell.display_menu_controller import DisplayMenuController
from chappy.presentation.spectrum import SpectrumDisplayOptions


@pytest.fixture()
def controller(qapp: QApplication) -> DisplayMenuController:
    """Return a display menu controller bound to the test application.

    Args:
        qapp: Qt application owning the created actions.

    Returns:
        Controller under test.
    """
    return DisplayMenuController(parent=qapp)


def _actions(controller: DisplayMenuController) -> tuple[QAction, QAction]:
    """Return the error-spectrum and component-profile actions.

    Args:
        controller: Controller under test.

    Returns:
        The two display toggle actions in menu order.
    """
    error_action, component_action = controller.actions()
    return error_action, component_action


def test_toggling_an_action_emits_the_selected_options(controller: DisplayMenuController) -> None:
    """User toggles publish the full display option set."""
    error_action, component_action = _actions(controller)
    emissions: list[SpectrumDisplayOptions] = []
    controller.display_options_changed.connect(emissions.append)

    error_action.setChecked(False)
    component_action.setChecked(True)

    assert emissions == [
        SpectrumDisplayOptions(show_error_spectrum=False, show_component_profiles=False),
        SpectrumDisplayOptions(show_error_spectrum=False, show_component_profiles=True),
    ]
    assert controller.options() == emissions[-1]


def test_set_options_restores_state_without_emitting(controller: DisplayMenuController) -> None:
    """Restored options update the checks but must not re-apply them downstream."""
    error_action, component_action = _actions(controller)
    emissions: list[SpectrumDisplayOptions] = []
    controller.display_options_changed.connect(emissions.append)

    controller.set_options(
        SpectrumDisplayOptions(show_error_spectrum=False, show_component_profiles=True)
    )

    assert emissions == []
    assert not error_action.isChecked()
    assert component_action.isChecked()


def test_unsupported_component_profiles_disable_the_action_but_keep_its_state(
    controller: DisplayMenuController,
) -> None:
    """Losing mode capability disables the toggle without discarding the user choice."""
    _, component_action = _actions(controller)
    controller.set_component_profiles_supported(True)
    component_action.setChecked(True)

    controller.set_component_profiles_supported(False)

    assert not component_action.isEnabled()
    assert component_action.isChecked()
    assert component_action.toolTip() == "Available in Analysis region detail"

    controller.set_component_profiles_supported(True)

    assert component_action.isEnabled()


def test_component_profiles_shortcut_toggles_only_while_the_action_is_enabled(
    controller: DisplayMenuController, qtbot: QtBot
) -> None:
    """Pressing M routes through the panel to the action, but only while it is enabled."""
    panel = DataControlPanel()
    panel.attach_display_menu(controller.actions())
    window = QMainWindow()
    window.setCentralWidget(panel)
    qtbot.addWidget(window)
    with qtbot.waitExposed(window):
        window.show()
    with qtbot.waitActive(window):
        window.raise_()
        window.activateWindow()
    panel.setFocus()

    controller.set_component_profiles_supported(True)
    qtbot.keyClick(panel, Qt.Key.Key_M)

    assert controller.options().show_component_profiles is True

    controller.set_component_profiles_supported(False)
    qtbot.keyClick(panel, Qt.Key.Key_M)

    assert controller.options().show_component_profiles is True
