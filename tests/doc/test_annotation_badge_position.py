"""Tests for manual screenshot annotation badge placement."""

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QWidget

from chappy_user_manual_generator.exporter import DocItem, _annotation_badge_rect


def _item(widget: QWidget) -> DocItem:
    return DocItem(
        widget=widget,
        rect=QRect(0, 0, 100, 30),
        label="Mask panel",
        role="QFrame",
        description="Mask controls",
        shortcut="",
        object_name="optimizeMaskPanel",
        class_name="QFrame",
    )


def test_annotation_badge_can_be_placed_outside_left(qtbot) -> None:
    """An outside badge leaves a left-aligned section title unobscured."""
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.setProperty("doc.badgePosition", "outside-left")
    annotated_rect = QRect(200, 40, 300, 24)

    badge = _annotation_badge_rect(_item(widget), annotated_rect)

    assert badge.right() == annotated_rect.left() - 1
    assert not badge.intersects(annotated_rect)


def test_annotation_badge_falls_back_inside_when_left_space_is_unavailable(qtbot) -> None:
    """Badges remain visible when an annotated rectangle touches the image edge."""
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.setProperty("doc.badgePosition", "outside-left")
    annotated_rect = QRect(0, 40, 300, 24)

    badge = _annotation_badge_rect(_item(widget), annotated_rect)

    assert badge.topLeft() == annotated_rect.topLeft()
