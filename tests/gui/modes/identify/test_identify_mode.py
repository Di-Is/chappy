"""Tests for identify mode module boundaries."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.common import ModeRefreshRequest
from chappy.gui.modes.identify import IdentifyModeLifecycle, create_identify_registration
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


class _IdentifyWorkflowPort:
    """Record identify workflow operations requested by mode lifecycle objects."""

    def __init__(self) -> None:
        """Initialize captured calls."""
        self.calls: list[str] = []

    def activate_identify_workflow(self) -> None:
        """Record identify workflow activation."""
        self.calls.append("activate")

    def deactivate_identify_workflow(self) -> None:
        """Record identify workflow deactivation."""
        self.calls.append("deactivate")


def test_identify_lifecycle_accepts_own_refresh() -> None:
    """Verify identify lifecycle accepts identify refresh requests."""
    overlay_port = _LineOverlayPort()
    continuum_port = _ContinuumPort()
    workflow_port = _IdentifyWorkflowPort()
    lifecycle = IdentifyModeLifecycle(overlay_port, continuum_port, workflow_port)
    request = ModeRefreshRequest(mode=EditingMode.IDENTIFY, reason="test")

    lifecycle.activate()
    lifecycle.refresh(request)
    lifecycle.deactivate()

    assert lifecycle.active is False
    assert lifecycle.last_refresh == request
    assert overlay_port.calls == ["identify", "identify"]
    assert continuum_port.calls == ["hide", "hide"]
    assert workflow_port.calls == ["activate", "activate", "deactivate"]


def test_identify_lifecycle_rejects_other_mode_refresh() -> None:
    """Verify identify lifecycle rejects another mode refresh."""
    lifecycle = IdentifyModeLifecycle(
        _LineOverlayPort(), _ContinuumPort(), _IdentifyWorkflowPort()
    )

    with pytest.raises(ValueError, match="IdentifyModeLifecycle"):
        lifecycle.refresh(ModeRefreshRequest(mode=EditingMode.ANALYSIS, reason="test"))


def test_identify_panel_registration_mounts_widget(qtbot: QtBot) -> None:
    """Verify identify panel registration can be mounted into ModeSidePanelHost."""
    host = ModeSidePanelHost()
    panel = QWidget()
    lifecycle = IdentifyModeLifecycle(
        _LineOverlayPort(), _ContinuumPort(), _IdentifyWorkflowPort()
    )
    qtbot.addWidget(host)

    host.register_panel_entry(create_identify_registration(panel, lifecycle))
    host.activate_mode(EditingMode.IDENTIFY)

    assert host._stack.currentWidget() is panel
    assert panel.objectName() == "modeSidePanel_identify"
