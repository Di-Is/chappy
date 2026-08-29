"""Tests for the velocity display-range session controller and input widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

from chappy.gui.spectrum.velocity import (
    VelocityDisplayHalfWidthSpinBox,
    VelocityDisplayInputRejection,
    VelocityDisplayRangeController,
)
from chappy.presentation.velocity import (
    VelocityDisplayHalfWidth,
    VelocityDisplayRangeState,
    VelocityDisplayScopeKey,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def test_controller_preserves_manual_range_across_refresh_page_and_region() -> None:
    """Session refresh should not copy changed analysis ranges into a manual view."""
    applied: list[VelocityDisplayHalfWidth] = []
    states: list[VelocityDisplayRangeState | None] = []
    controller = VelocityDisplayRangeController(
        apply_display_half_width=applied.append, state_changed=states.append
    )
    region_a = VelocityDisplayScopeKey("region-a")
    region_b = VelocityDisplayScopeKey("region-b")
    controller.activate(region_a, (230.0, 180.0))
    controller.commit_manual(VelocityDisplayHalfWidth(600.0))

    controller.activate(region_a, (1000.0,))
    controller.activate(region_b, (1500.0,))

    assert [value.value for value in applied] == [250.0, 600.0, 600.0, 600.0]
    assert states[-1] is not None
    assert states[-1].scope_key == "region-b"
    assert states[-1].source == "manual"

    controller.fit_view_to_analysis_ranges()
    assert applied[-1].value == 1750.0
    assert states[-1] is not None
    assert states[-1].source == "auto"

    controller.clear()
    assert controller.state is None
    assert states[-1] is None


def test_spinbox_step_rejects_endpoint_without_clamping(qtbot: QtBot) -> None:
    """Spin buttons and arrow keys should restore the previous accepted endpoint."""
    spinbox = VelocityDisplayHalfWidthSpinBox()
    qtbot.addWidget(spinbox)
    spinbox.set_accepted_value(VelocityDisplayHalfWidth(10.0))
    rejections: list[VelocityDisplayInputRejection] = []
    spinbox.input_rejected.connect(rejections.append)

    spinbox.setFocus()
    qtbot.keyClick(spinbox, Qt.Key.Key_Down)

    assert spinbox.accepted_value.value == 10.0
    assert spinbox.value() == 10.0
    assert rejections[-1].reason == "outside_supported_range"


def test_spinbox_keyboard_input_commits_typed_value(qtbot: QtBot) -> None:
    """Completed keyboard input should emit a validated presentation value."""
    spinbox = VelocityDisplayHalfWidthSpinBox()
    qtbot.addWidget(spinbox)
    accepted: list[VelocityDisplayHalfWidth] = []
    spinbox.value_accepted.connect(accepted.append)

    editor = spinbox.lineEdit()
    editor.selectAll()
    qtbot.keyClicks(editor, "725")
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert accepted[-1] == VelocityDisplayHalfWidth(725.0)
    assert spinbox.accepted_value.value == 725.0


def test_spinbox_keyboard_input_restores_out_of_range_value(qtbot: QtBot) -> None:
    """Out-of-range keyboard text should be rejected rather than clamped to 5000."""
    spinbox = VelocityDisplayHalfWidthSpinBox()
    qtbot.addWidget(spinbox)
    spinbox.set_accepted_value(VelocityDisplayHalfWidth(500.0))
    rejections: list[VelocityDisplayInputRejection] = []
    spinbox.input_rejected.connect(rejections.append)

    editor = spinbox.lineEdit()
    editor.selectAll()
    qtbot.keyClicks(editor, "6000")
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert spinbox.accepted_value.value == 500.0
    assert spinbox.value() == 500.0
    assert rejections[-1].reason == "outside_supported_range"
