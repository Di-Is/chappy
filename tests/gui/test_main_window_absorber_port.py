"""Tests for main-window absorber editor port validation."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Signal

from chappy.gui.shell.main_window import MainWindow


class _AbsorberHost(QObject):
    """QObject carrying the absorber host signals required by the port."""

    component_added = Signal(object)
    parameter_changed = Signal(str, str, float)
    absorber_selected = Signal(str)


def _window() -> MainWindow:
    """Create an uninitialized main-window object for helper tests."""
    return MainWindow.__new__(MainWindow)


def test_absorber_editor_port_accepts_required_signal_surface() -> None:
    """A host exposing required absorber signals should pass validation."""
    host = _AbsorberHost()

    assert _window()._absorber_editor_port(host) is host


def test_absorber_editor_port_rejects_invalid_surface() -> None:
    """A wrong absorber editor payload should fail before signal wiring."""
    with pytest.raises(TypeError, match="absorber port"):
        _window()._absorber_editor_port(object())
