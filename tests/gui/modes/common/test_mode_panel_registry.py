"""Tests for common mode panel registry contracts."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common import ModePanelRegistry, ModeRefreshRequest
from chappy.gui.modes.identify import create_identify_registration
from chappy.gui.modes.mode_panel_host import ModeSidePanelHost


class _Lifecycle:
    """Minimal lifecycle used by registry tests."""

    def set_project(self, project: object | None) -> None:
        """Accept project changes."""

    def activate(self) -> None:
        """Activate lifecycle."""

    def deactivate(self) -> None:
        """Deactivate lifecycle."""

    def refresh(self, request: ModeRefreshRequest) -> None:
        """Accept refresh requests."""


def test_mode_panel_registry_installs_entries(qtbot: QtBot) -> None:
    """Verify registry installs entries into a mode panel host."""
    host = ModeSidePanelHost()
    panel = QWidget()
    registry = ModePanelRegistry()
    lifecycle = _Lifecycle()
    qtbot.addWidget(host)

    registry.register(create_identify_registration(panel, lifecycle))
    registry.install_into(host)
    host.activate_mode(EditingMode.IDENTIFY)

    assert host._stack.currentWidget() is panel
