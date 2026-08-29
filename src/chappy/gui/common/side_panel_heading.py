"""Shared styling for peer side-panel section headings."""

from PySide6.QtWidgets import QLabel

from chappy.gui.theme import Colors, Fonts


def apply_side_panel_heading_style(label: QLabel) -> None:
    """Apply the common hierarchy style to a side-panel section heading."""
    label.setStyleSheet(
        f"font-size: {Fonts.SIZE_MEDIUM}; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
    )
