"""Tests for manual screenshot annotation badge placement."""

from PySide6.QtCore import QRect

from chappy_user_manual_generator.exporter import _annotation_badge_rect

_IMAGE = QRect(0, 0, 800, 600)


def test_annotation_badge_is_placed_outside_left() -> None:
    """An outside badge leaves a left-aligned section title unobscured."""
    annotated_rect = QRect(200, 40, 300, 24)

    badge = _annotation_badge_rect(annotated_rect, [annotated_rect], _IMAGE)

    assert badge.right() == annotated_rect.left() - 1
    assert not badge.intersects(annotated_rect)


def test_annotation_badge_moves_above_when_left_space_is_occupied() -> None:
    """A badge avoids overlapping a neighbouring annotation on the left."""
    annotated_rect = QRect(200, 40, 300, 24)
    neighbour = QRect(150, 30, 40, 40)

    badge = _annotation_badge_rect(annotated_rect, [annotated_rect, neighbour], _IMAGE)

    assert badge.bottom() == annotated_rect.top() - 1
    assert not badge.intersects(neighbour)


def test_annotation_badge_ignores_enclosing_annotation() -> None:
    """An annotation containing the target is surroundings, not a collision."""
    annotated_rect = QRect(200, 40, 300, 24)
    enclosing = QRect(100, 0, 600, 200)

    badge = _annotation_badge_rect(annotated_rect, [annotated_rect, enclosing], _IMAGE)

    assert badge.right() == annotated_rect.left() - 1


def test_annotation_badge_falls_back_inside_when_no_outside_space_is_available() -> None:
    """Badges remain visible when an annotated rectangle fills the image."""
    annotated_rect = QRect(0, 0, 300, 24)

    badge = _annotation_badge_rect(annotated_rect, [annotated_rect], QRect(0, 0, 300, 24))

    assert badge.topLeft() == annotated_rect.topLeft()
