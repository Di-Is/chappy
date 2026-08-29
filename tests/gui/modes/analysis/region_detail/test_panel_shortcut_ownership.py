"""Shortcut ownership contract for the Region Detail panel."""

from __future__ import annotations

import inspect

from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from chappy.gui.shell.shortcuts import SHORTCUTS
from chappy.gui.shell.actions.ids import ShellActionId


def test_f5_is_owned_only_by_shell_action() -> None:
    """Region Detail must not install a second panel-local F5 shortcut."""
    install_source = inspect.getsource(RegionDetailPanel._install_shortcuts)

    assert "Key_F5" not in install_source
    assert "_optimize_shortcut" not in install_source
    assert SHORTCUTS[ShellActionId.FIT_MODEL].key == "F5"
