"""Tests for optimize editor statistics boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_get_fit_statistics_requires_current_project(qtbot: QtBot) -> None:
    """Fit statistics are not available without an active project."""
    editor = OptimizeEditor()
    qtbot.addWidget(editor)

    with pytest.raises(RuntimeError, match="Current project is required"):
        editor.get_fit_statistics()
