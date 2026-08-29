"""Table controller component for AbsorberEditor.

This module handles all table widget operations, inline editing, and row management
for absorption line components.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from chappy.core.validation_constants import PARAM_VALIDATION

if TYPE_CHECKING:
    from chappy.core.components.absorber import AbsorberComponent

logger = logging.getLogger(__name__)

# Table column indices (from original absorber_editor.py)
TABLE_COL_NAME = 0
TABLE_COL_WAVELENGTH = 1
TABLE_COL_REDSHIFT = 2
TABLE_COL_COLUMN_DENSITY = 3
TABLE_COL_B_PARAMETER = 4
TABLE_COL_GROUP = 5


class AbsorberTableController(QObject):
    """Control table widget operations and inline editing for absorber components.

    Handles creation and management of:
    - Table setup and configuration
    - Row operations (add, remove, update)
    - Inline editing handling
    - Table-to-model synchronization
    - Selection management
    """

    # Signals for table events
    selection_changed = Signal(str)  # absorber_name or empty string
    absorber_edited = Signal(str, str, float)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize table controller.

        Args:
            parent: Parent QObject
        """
        super().__init__(parent)
        self._table: QTableWidget | None = None
        self._updating_table = False
        self._absorber_rows: dict[str, int] = {}  # absorber_name -> row_index

        logger.debug("AbsorberTableController initialized")

    def create_table_widget(self) -> QTableWidget:
        """Create and configure a new table widget for absorbers.

        Returns:
            Configured QTableWidget for absorber display
        """
        table = QTableWidget()
        self.setup_table(table)
        return table

    def setup_table(self, table: QTableWidget) -> None:
        """Setup the absorber table widget with proper configuration.

        Args:
            table: QTableWidget to configure
        """
        self._table = table

        # Set column count and headers
        self._table.setColumnCount(6)
        headers = [
            self.tr("Name"),
            self.tr("λ [Å]"),
            self.tr("z"),
            self.tr("log N"),
            self.tr("b"),
            self.tr("Group"),
        ]
        self._table.setHorizontalHeaderLabels(headers)

        # Configure table properties
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)

        # Set header properties
        header = self._table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name column
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Wavelength
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Redshift
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Column density
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # B parameter
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Group

        # Connect signals
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemChanged.connect(self._on_item_changed)

        logger.debug("Table setup completed")

    def _require_table(self, operation: str) -> QTableWidget:
        """Return the configured table or fail fast for required table operations."""
        if self._table is None:
            msg = f"Absorber table is required for {operation}."
            raise RuntimeError(msg)
        return self._table

    def add_absorber(self, absorber: AbsorberComponent) -> None:
        """Add an absorber component to the table.

        Args:
            absorber: Absorber to add to table
        """
        table = self._require_table("add_absorber")

        # Add new row
        row = table.rowCount()
        table.insertRow(row)

        # Update absorber row mapping
        self._absorber_rows[absorber.name] = row

        # Add absorber data to table
        self.update_absorber(absorber)

        logger.debug("Added absorber to table", extra={"absorber_name": absorber.name, "row": row})

    def update_absorber(self, absorber: AbsorberComponent, group_name: str | None = None) -> None:
        """Update a table row with absorber data.

        Args:
            absorber: Absorber component with data
            group_name: Optional group name to display
        """
        table = self._require_table("update_absorber")
        if absorber.name not in self._absorber_rows:
            return

        row = self._absorber_rows[absorber.name]
        self._updating_table = True

        try:
            # Name column (editable)
            name_item = QTableWidgetItem(absorber.name)
            name_item.setData(Qt.ItemDataRole.UserRole, absorber.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, TABLE_COL_NAME, name_item)

            # Wavelength column (read-only)
            wavelength = absorber.wavelength
            wavelength_item = QTableWidgetItem(f"{wavelength:.2f}")
            wavelength_item.setFlags(wavelength_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, TABLE_COL_WAVELENGTH, wavelength_item)

            # Redshift column (editable)
            redshift = absorber.parameters["redshift"].value
            redshift_item = QTableWidgetItem(f"{redshift:.6f}")
            redshift_item.setData(Qt.ItemDataRole.UserRole, redshift)
            table.setItem(row, TABLE_COL_REDSHIFT, redshift_item)

            # Column density column (editable)
            column_density = absorber.parameters["column_density"].value
            column_density_item = QTableWidgetItem(f"{column_density:.2f}")
            column_density_item.setData(Qt.ItemDataRole.UserRole, column_density)
            table.setItem(row, TABLE_COL_COLUMN_DENSITY, column_density_item)

            # B parameter column (editable)
            b_parameter = absorber.parameters["b_parameter"].value
            b_parameter_item = QTableWidgetItem(f"{b_parameter:.1f}")
            b_parameter_item.setData(Qt.ItemDataRole.UserRole, b_parameter)
            table.setItem(row, TABLE_COL_B_PARAMETER, b_parameter_item)

            # Group column (read-only)
            group_item = QTableWidgetItem(group_name or "None")
            group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, TABLE_COL_GROUP, group_item)

        finally:
            self._updating_table = False

        logger.debug("Updated absorber in table", extra={"absorber_name": absorber.name})

    def get_selected_absorber(self) -> str | None:
        """Get the name of the currently selected absorber.

        Returns:
            Name of selected absorber or None if no selection
        """
        if not self._table:
            return None

        current_row = self._table.currentRow()
        if current_row >= 0:
            name_item = self._table.item(current_row, TABLE_COL_NAME)
            if name_item:
                data = name_item.data(Qt.ItemDataRole.UserRole)
                return str(data) if data is not None else None

        return None

    def refresh_table(self) -> None:
        """Refresh the table display (placeholder for project-based refresh)."""
        table = self._require_table("refresh_table")

        # For now, just ensure table is visible and updated
        table.viewport().update()
        logger.debug("Table refreshed")

    def update_absorber_parameter(
        self, absorber_name: str, parameter_name: str, value: float
    ) -> None:
        """Update a specific parameter value in the table.

        Args:
            absorber_name: Name of absorber
            parameter_name: Name of parameter to update
            value: New parameter value
        """
        table = self._require_table("update_absorber_parameter")
        if absorber_name not in self._absorber_rows:
            return

        row = self._absorber_rows[absorber_name]
        self._updating_table = True

        try:
            if parameter_name == "redshift":
                item = QTableWidgetItem(f"{value:.6f}")
                item.setData(Qt.ItemDataRole.UserRole, value)
                table.setItem(row, TABLE_COL_REDSHIFT, item)
            elif parameter_name == "column_density":
                item = QTableWidgetItem(f"{value:.2f}")
                item.setData(Qt.ItemDataRole.UserRole, value)
                table.setItem(row, TABLE_COL_COLUMN_DENSITY, item)
            elif parameter_name == "b_parameter":
                item = QTableWidgetItem(f"{value:.1f}")
                item.setData(Qt.ItemDataRole.UserRole, value)
                table.setItem(row, TABLE_COL_B_PARAMETER, item)
        finally:
            self._updating_table = False

        logger.debug(
            "Updated parameter for absorber",
            extra={"parameter_name": parameter_name, "absorber_name": absorber_name},
        )

    def clear_table(self) -> None:
        """Clear all rows from the table."""
        table = self._require_table("clear_table")

        table.setRowCount(0)
        self._absorber_rows.clear()

        logger.debug("Cleared all rows from table")

    def _on_selection_changed(self) -> None:
        """Handle table selection changes."""
        self._require_table("selection change handling")

        selected_absorber = self.get_selected_absorber()
        self.selection_changed.emit(selected_absorber or "")

        logger.debug("Table selection changed", extra={"selected_absorber": selected_absorber})

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle table item changes (inline editing).

        Args:
            item: Changed table item
        """
        if self._updating_table:
            return

        table = self._require_table("item change handling")
        row = item.row()
        column = item.column()

        # Get absorber name from the row
        name_item = table.item(row, TABLE_COL_NAME)
        if not name_item:
            return

        absorber_name_data = name_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(absorber_name_data, str):
            return

        try:
            self._handle_column_edit(item, column, absorber_name_data)
        except (ValueError, TypeError) as e:
            logger.warning("Invalid value entered in table", extra={"error": str(e)})
            self._revert_item(item, column, absorber_name_data)

    def _handle_column_edit(self, item: QTableWidgetItem, column: int, absorber_name: str) -> None:
        """Handle editing of specific table columns.

        Args:
            item: The table item being edited
            column: Column index
            absorber_name: Name of the absorber being edited
        """
        if column == TABLE_COL_NAME:
            # Name column is read-only; restore original text.
            self._revert_item(item, column, absorber_name)
            return
        if column == TABLE_COL_REDSHIFT:
            self._handle_parameter_edit(item, absorber_name, "redshift")
        elif column == TABLE_COL_COLUMN_DENSITY:
            self._handle_parameter_edit(item, absorber_name, "column_density")
        elif column == TABLE_COL_B_PARAMETER:
            self._handle_parameter_edit(item, absorber_name, "b_parameter")
        elif column == TABLE_COL_GROUP:
            # Group column is read-only - ignore edits
            pass
        else:
            # Wavelength column is read-only - ignore edits
            pass

    def _handle_parameter_edit(
        self, item: QTableWidgetItem, absorber_name: str, param_name: str
    ) -> None:
        """Handle parameter column editing.

        Args:
            item: The table item being edited
            absorber_name: Name of absorber being edited
            param_name: Name of parameter being edited
        """
        try:
            value = float(item.text())

            # Basic validation
            if param_name == "redshift" and not (
                PARAM_VALIDATION.REDSHIFT_MIN <= value <= PARAM_VALIDATION.REDSHIFT_MAX
            ):
                msg = f"Redshift must be between {PARAM_VALIDATION.REDSHIFT_MIN} and {PARAM_VALIDATION.REDSHIFT_MAX}"
                raise ValueError(msg)  # noqa: TRY301
            if param_name == "column_density" and not (
                PARAM_VALIDATION.COLUMN_DENSITY_MIN <= value <= PARAM_VALIDATION.COLUMN_DENSITY_MAX
            ):
                msg = f"Column density must be between {PARAM_VALIDATION.COLUMN_DENSITY_MIN} and {PARAM_VALIDATION.COLUMN_DENSITY_MAX}"
                raise ValueError(msg)  # noqa: TRY301
            if param_name == "b_parameter" and not (
                PARAM_VALIDATION.B_PARAMETER_MIN <= value <= PARAM_VALIDATION.B_PARAMETER_MAX
            ):
                msg = f"B parameter must be between {PARAM_VALIDATION.B_PARAMETER_MIN} and {PARAM_VALIDATION.B_PARAMETER_MAX} km/s"
                raise ValueError(msg)  # noqa: TRY301

            # Store the value and emit signal
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.absorber_edited.emit(absorber_name, param_name, value)

        except ValueError as e:
            logger.warning(
                "Invalid parameter value", extra={"param_name": param_name, "error": str(e)}
            )
            raise

    def _revert_item(self, item: QTableWidgetItem, column: int, absorber_name: str) -> None:
        """Revert a table item to its original value.

        Args:
            item: Table item to revert
            column: Column index
            absorber_name: Name of absorber
        """
        # Get the original value from UserRole data
        original_value = item.data(Qt.ItemDataRole.UserRole)

        if column == TABLE_COL_NAME:
            item.setText(absorber_name)
        elif original_value is not None:
            if column == TABLE_COL_REDSHIFT:
                item.setText(f"{original_value:.6f}")
            elif column == TABLE_COL_COLUMN_DENSITY:
                item.setText(f"{original_value:.2f}")
            elif column == TABLE_COL_B_PARAMETER:
                item.setText(f"{original_value:.1f}")

        logger.debug(
            "Reverted table item", extra={"absorber_name": absorber_name, "column": column}
        )
