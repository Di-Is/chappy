"""Layout builder component for AbsorberEditor.

This module handles all user interface creation, layout management, and styling
for absorption line components.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.theme import (
    ButtonVariant,
    apply_button_variant,
    checkbox_style,
    group_box_style,
    input_style,
)

logger = logging.getLogger(__name__)

type StyleGroup = dict[str, str]
type AbsorberEditorStyleConfig = dict[str, StyleGroup]


class AbsorberEditorLayout(QObject):
    """Build absorber editor layouts and apply widget styling."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize absorber editor layout builder.

        Args:
            parent: Parent QObject
        """
        super().__init__(parent)
        self._controls: dict[str, QPushButton | QDoubleSpinBox | QComboBox | QCheckBox] = {}
        self._layouts: dict[str, QVBoxLayout | QHBoxLayout] = {}

        logger.debug("AbsorberEditorLayout initialized")

    def setup_main_ui(self, parent_widget: QWidget) -> QVBoxLayout:
        """Setup the main user interface layout.

        Args:
            parent_widget: Parent widget to contain the UI

        Returns:
            Main layout for the absorber editor UI
        """
        main_layout = QVBoxLayout(parent_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)

        self._layouts["main"] = main_layout

        logger.debug("Main UI layout created")

        return main_layout

    def create_header_section(self) -> tuple[QHBoxLayout, dict[str, QPushButton]]:
        """Create header section with controls and buttons.

        Returns:
            Tuple of (header_layout, control_buttons)
        """
        header_layout = QHBoxLayout()

        # Title label
        title_label = QLabel("Absorption Lines")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self._layouts["header"] = header_layout

        logger.debug("Header section created with controls")

        return header_layout, {}

    def setup_absorber_table(self, table: QTableWidget) -> None:
        """Setup absorber table widget configuration.

        Args:
            table: Table widget to configure
        """
        if not isinstance(table, QTableWidget):
            msg = "Absorber table setup requires a QTableWidget."
            raise TypeError(msg)

        # Set column count and headers
        table.setColumnCount(6)
        headers = [
            self.tr("Name"),
            self.tr("λ [Å]"),
            self.tr("z"),
            self.tr("log N"),
            self.tr("b"),
            self.tr("Group"),
        ]
        table.setHorizontalHeaderLabels(headers)

        # Configure table properties
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)

        # Set header properties
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name column
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Wavelength
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Redshift
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Column density
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # B parameter
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Group

        # Add context menu capability
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        logger.debug("Absorber table configured")

    def apply_styling(self, style_config: AbsorberEditorStyleConfig | None = None) -> None:
        """Apply styling to UI elements.

        Args:
            style_config: Optional style configuration dictionary
        """
        if not style_config:
            style_config = self._get_default_style_config()

        # Apply button variants
        for control_name, control in self._controls.items():
            if isinstance(control, QPushButton):
                apply_button_variant(control, self._get_button_type(control_name))

        # Apply input styles
        for control in self._controls.values():
            input_styles = style_config.get("inputs")
            if isinstance(control, QDoubleSpinBox | QComboBox) and input_styles is not None:
                control.setStyleSheet(input_styles["default"])

        # Apply checkbox styles
        for control in self._controls.values():
            checkbox_styles = style_config.get("checkboxes")
            if isinstance(control, QCheckBox) and checkbox_styles is not None:
                control.setStyleSheet(checkbox_styles["default"])

        # Apply group box styles
        logger.debug("UI styling applied")

    def _get_default_style_config(self) -> AbsorberEditorStyleConfig:
        """Get default style configuration.

        Returns:
            Default style configuration dictionary
        """
        return {
            "inputs": {"default": input_style()},
            "checkboxes": {"default": checkbox_style()},
            "group_boxes": {"default": group_box_style()},
        }

    def _get_button_type(self, control_name: str) -> ButtonVariant:
        """Determine button variant based on control name.

        Args:
            control_name: Name of button control

        Returns:
            Button variant for styling
        """
        if "remove" in control_name.lower():
            return "danger"
        if "add" in control_name.lower():
            return "primary"
        return "secondary"
