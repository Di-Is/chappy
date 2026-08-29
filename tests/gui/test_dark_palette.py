"""Tests for the dark QPalette covering every color role."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QPalette

from chappy.gui.theme import Colors, create_dark_palette

ALL_ROLES = [
    role
    for role in QPalette.ColorRole
    if role not in (QPalette.ColorRole.NoRole, QPalette.ColorRole.NColorRoles)
]

ALL_GROUPS = [
    QPalette.ColorGroup.Active,
    QPalette.ColorGroup.Inactive,
    QPalette.ColorGroup.Disabled,
]


@pytest.mark.parametrize("role", ALL_ROLES, ids=lambda role: role.name)
@pytest.mark.parametrize("group", ALL_GROUPS, ids=lambda group: group.name)
def test_every_role_is_set_in_every_group(
    group: QPalette.ColorGroup, role: QPalette.ColorRole
) -> None:
    palette = create_dark_palette()

    assert palette.isBrushSet(group, role)


def test_link_color_is_not_qt_default_navy() -> None:
    palette = create_dark_palette()

    assert palette.color(QPalette.ColorRole.Link) == QColor(Colors.PRIMARY)
