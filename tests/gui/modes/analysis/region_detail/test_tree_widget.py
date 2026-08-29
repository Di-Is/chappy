"""Tests for the optimize parameter tree widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.gui.modes.analysis.region_detail.tree.tree_widget import OptimizeTreeWidget

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_resize_announces_the_new_viewport_width(qtbot: QtBot) -> None:
    """Column widths can only be redistributed if resizes are announced.

    The width is redistributed from this signal rather than from the header's
    own ``geometriesChanged``, which Qt also emits while tearing the widget
    down and which therefore cannot carry a Python receiver safely.
    """
    tree = OptimizeTreeWidget()
    qtbot.addWidget(tree)
    tree.resize(400, 300)
    tree.show()

    with qtbot.waitSignal(tree.viewport_resized, timeout=1000):
        tree.resize(800, 300)
