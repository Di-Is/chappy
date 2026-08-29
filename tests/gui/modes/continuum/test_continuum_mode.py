"""Tests for continuum mode module boundaries."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common import ModeRefreshRequest
from chappy.gui.modes.continuum import ContinuumModeLifecycle, create_continuum_registration
from chappy.gui.modes.mode_panel_host import ModeSidePanelHost


class _LineOverlayPort:
    """Record line overlay operations requested by mode lifecycle objects."""

    def __init__(self) -> None:
        """Initialize captured calls."""
        self.calls: list[str] = []

    def show_confirmed_line_overlays(self) -> None:
        """Record confirmed overlay request."""
        self.calls.append("confirmed")

    def show_identify_line_overlays(self) -> None:
        """Record identify overlay request."""
        self.calls.append("identify")

    def clear_line_overlays(self) -> None:
        """Record clear request."""
        self.calls.append("clear")


class _ContinuumPort:
    """Record continuum operations requested by mode lifecycle objects."""

    def __init__(self) -> None:
        """Initialize captured calls."""
        self.calls: list[str] = []

    def show_continuum(self) -> None:
        """Record show request."""
        self.calls.append("show")

    def hide_continuum(self) -> None:
        """Record hide request."""
        self.calls.append("hide")


def test_continuum_lifecycle_accepts_own_refresh() -> None:
    """Verify continuum lifecycle accepts continuum refresh requests."""
    overlay_port = _LineOverlayPort()
    continuum_port = _ContinuumPort()
    lifecycle = ContinuumModeLifecycle(overlay_port, continuum_port)
    request = ModeRefreshRequest(mode=EditingMode.CONTINUUM, reason="test")

    lifecycle.activate()
    lifecycle.refresh(request)

    assert lifecycle.active is True
    assert lifecycle.last_refresh == request
    assert overlay_port.calls == ["clear", "clear"]
    assert continuum_port.calls == ["show", "show"]


def test_continuum_lifecycle_rejects_other_mode_refresh() -> None:
    """Verify continuum lifecycle rejects another mode refresh."""
    lifecycle = ContinuumModeLifecycle(_LineOverlayPort(), _ContinuumPort())

    with pytest.raises(ValueError, match="ContinuumModeLifecycle"):
        lifecycle.refresh(ModeRefreshRequest(mode=EditingMode.ANALYSIS, reason="test"))


def test_continuum_panel_registration_mounts_widget(qtbot: QtBot) -> None:
    """Verify continuum panel registration can be mounted into ModeSidePanelHost."""
    host = ModeSidePanelHost()
    panel = QWidget()
    lifecycle = ContinuumModeLifecycle(_LineOverlayPort(), _ContinuumPort())
    qtbot.addWidget(host)

    host.register_panel_entry(create_continuum_registration(panel, lifecycle))
    host.activate_mode(EditingMode.CONTINUUM)

    assert host._stack.currentWidget() is panel
    assert panel.objectName() == "modeSidePanel_continuum"
