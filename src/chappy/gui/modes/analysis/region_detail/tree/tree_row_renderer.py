"""Renderer for optimize tree rows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTreeWidgetItem

from chappy.core.absorption_display import iter_component_display_rows
from chappy.core.cosmology import comoving_distance_mpc, lookback_time_gyr
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    ROLE_EDIT_KIND,
    ROLE_LINE_IDS,
    ROLE_RAW_ERROR,
    ROLE_RAW_VALUE,
    TreeCellEditKind,
)
from chappy.gui.modes.analysis.region_detail.tree.uncertainty_format import format_value_with_error
from chappy.gui.theme import Colors

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.base import Parameter
    from chappy.core.cosmology import CosmologyParameters


# Format specs mirror the LOOKBACK/COMOVING ColumnMeta entries in tree_columns.py.
_LOOKBACK_FORMAT = "{:.3f}"
_COMOVING_FORMAT = "{:.1f}"

# Placeholder for parameter cells that have no value on line rows; matches the
# Overview review table's em-dash convention so empty cells do not look broken.
_EMPTY_CELL_PLACEHOLDER = "—"


@dataclass(frozen=True, slots=True)
class OptimizeTreeParameterColumn:
    """Column mapping for one rendered absorber parameter."""

    name: str
    value_column: int
    value_format: str
    default_value: float


@dataclass(frozen=True, slots=True)
class OptimizeTreeRowColumns:
    """Column layout required by the optimize tree row renderer."""

    column_count: int
    id_column: int
    species_column: int
    redshift_column: int
    wavelength_column: int
    lookback_column: int
    comoving_column: int
    analysis_half_width_column: int
    parameter_columns: tuple[OptimizeTreeParameterColumn, ...]


class OptimizeTreeRowRenderPort(Protocol):
    """Panel operations required by tree row rendering."""

    def tree_display_name_for_line(self, line: AbsorptionLine) -> str:
        """Return the display label for an absorption line row."""
        ...

    def ensure_tree_covering_factor_parameter(self, component: AbsorberComponent) -> None:
        """Ensure the component has a covering factor parameter."""
        ...

    def apply_tree_parameter_styles(self, item: QTreeWidgetItem) -> None:
        """Apply parameter-related cell styles to a rendered model row."""
        ...

    def tie_label_for(self, component: AbsorberComponent, parameter_name: str) -> str | None:
        """Return the tie-set display label for a masked parameter cell, if tied."""
        ...

    def tie_tooltip_for(self, component: AbsorberComponent, parameter_name: str) -> str | None:
        """Return the tie-set tooltip text for a masked parameter cell, if tied."""
        ...

    def is_tree_component_stale(self, component: AbsorberComponent) -> bool:
        """Return whether the component needs re-optimization."""
        ...

    def tree_cosmology_parameters(self) -> CosmologyParameters:
        """Return the cosmology parameters used to compute lookback/comoving columns."""
        ...


class OptimizeTreeRowRenderer:
    """Populate optimize tree widget items from domain values."""

    def __init__(
        self, *, columns: OptimizeTreeRowColumns, port: OptimizeTreeRowRenderPort
    ) -> None:
        """Initialize the row renderer.

        Args:
            columns: Tree column layout.
            port: Panel-specific display and style operations.
        """
        self._columns = columns
        self._port = port

    def populate_multiplet_row(
        self,
        parent_item: QTreeWidgetItem,
        lines: tuple[AbsorptionLine, ...],
        display_index: int,
        component_index: Mapping[str, AbsorberComponent],
    ) -> None:
        """Populate a grouped line row and its component children."""
        if len(lines) == 1:
            self.populate_line_row(parent_item, lines[0], display_index)
            for _line, component, model_index in iter_component_display_rows(
                lines, component_index.get
            ):
                child = QTreeWidgetItem(parent_item)
                self.populate_model_row(child, component, model_index)
            return

        parent_item.setText(self._columns.id_column, str(display_index))
        parent_item.setText(self._columns.species_column, lines[0].multiplet_label)
        parent_item.setText(self._columns.redshift_column, f"{lines[0].center_z:.5f}")

        obs_min = min(line.rest_wavelength * (1.0 + line.center_z) for line in lines)
        obs_max = max(line.rest_wavelength * (1.0 + line.center_z) for line in lines)
        parent_item.setText(self._columns.wavelength_column, f"{obs_min:.2f}-{obs_max:.2f}")
        self._set_cosmology_columns(parent_item, lines[0].center_z)
        self._clear_line_parameter_columns(parent_item)
        self._set_line_analysis_half_width(parent_item, lines)
        self._apply_line_row_style(parent_item)
        parent_item.setData(0, Qt.ItemDataRole.UserRole, lines[0])
        parent_item.setData(
            self._columns.analysis_half_width_column,
            ROLE_LINE_IDS,
            tuple(line.line_id for line in lines),
        )

        for line, component, line_component_index in iter_component_display_rows(
            lines, component_index.get
        ):
            child = QTreeWidgetItem(parent_item)
            self.populate_model_row(
                child,
                component,
                line_component_index,
                species_label=f"{line.rest_wavelength:.0f} c{line_component_index}",
            )

    def populate_line_row(
        self, parent_item: QTreeWidgetItem, line: AbsorptionLine, display_index: int
    ) -> None:
        """Populate a single absorption line row."""
        parent_item.setText(self._columns.id_column, str(display_index))
        parent_item.setText(
            self._columns.species_column, self._port.tree_display_name_for_line(line)
        )
        parent_item.setText(self._columns.redshift_column, f"{line.center_z:.5f}")

        observed_wavelength = line.rest_wavelength * (1.0 + line.center_z)
        parent_item.setText(self._columns.wavelength_column, f"{observed_wavelength:.2f}")
        self._set_cosmology_columns(parent_item, line.center_z)
        self._clear_line_parameter_columns(parent_item)
        self._set_line_analysis_half_width(parent_item, (line,))
        self._apply_line_row_style(parent_item)
        parent_item.setData(0, Qt.ItemDataRole.UserRole, line)
        parent_item.setData(
            self._columns.analysis_half_width_column, ROLE_LINE_IDS, (line.line_id,)
        )

    def populate_model_row(
        self,
        item: QTreeWidgetItem,
        component: AbsorberComponent,
        model_index: int = 1,
        *,
        species_label: str | None = None,
    ) -> None:
        """Populate a component child row.

        Args:
            item: Tree item to populate.
            component: Component rendered on the row.
            model_index: Ordinal of the component within its line.
            species_label: Species-column text override; consolidated multiplet
                rows prefix the transition rest wavelength (e.g. ``2796 c1``).
        """
        item.setText(self._columns.species_column, species_label or f"c{model_index}")
        self.refresh_model_row(item, component)

    def refresh_model_row(self, item: QTreeWidgetItem, component: AbsorberComponent) -> None:
        """Refresh a rendered component row from a current component."""
        self._port.ensure_tree_covering_factor_parameter(component)

        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

        is_stale = self._port.is_tree_component_stale(component)

        for parameter_column in self._columns.parameter_columns:
            value = self._parameter_value(
                component, parameter_column.name, default=parameter_column.default_value
            )
            param_obj = component.parameters.get(parameter_column.name)
            error_value = None if is_stale else self._parameter_error_value(param_obj)

            formatted_value = format_value_with_error(
                value, error_value, parameter_column.value_format
            )
            label = self._port.tie_label_for(component, parameter_column.name)
            item.setText(
                parameter_column.value_column,
                f"[{label}] {formatted_value}" if label is not None else formatted_value,
            )
            item.setData(
                parameter_column.value_column, Qt.ItemDataRole.UserRole, parameter_column.name
            )
            item.setData(
                parameter_column.value_column, ROLE_EDIT_KIND, TreeCellEditKind.COMPONENT_PARAMETER
            )
            item.setData(parameter_column.value_column, ROLE_RAW_VALUE, value)
            item.setData(parameter_column.value_column, ROLE_RAW_ERROR, error_value)

            item.setToolTip(
                parameter_column.value_column,
                self._value_cell_tooltip(component, parameter_column.name, param_obj, is_stale),
            )

        item.setText(
            self._columns.wavelength_column, f"{self._observed_wavelength(component):.2f}"
        )
        self._set_cosmology_columns(item, self._parameter_value(component, "redshift"))
        item.setData(0, Qt.ItemDataRole.UserRole, component)
        item.setText(self._columns.analysis_half_width_column, "")
        item.setData(
            self._columns.analysis_half_width_column, ROLE_EDIT_KIND, TreeCellEditKind.NONE
        )
        self._port.apply_tree_parameter_styles(item)

    def _set_cosmology_columns(self, item: QTreeWidgetItem, redshift: float) -> None:
        """Render lookback time and comoving distance derived from a redshift."""
        params = self._port.tree_cosmology_parameters()
        item.setText(
            self._columns.lookback_column,
            _LOOKBACK_FORMAT.format(lookback_time_gyr(redshift, params)),
        )
        item.setText(
            self._columns.comoving_column,
            _COMOVING_FORMAT.format(comoving_distance_mpc(redshift, params)),
        )

    def _value_cell_tooltip(
        self,
        component: AbsorberComponent,
        parameter_name: str,
        param_obj: Parameter | None,
        is_stale: bool,
    ) -> str:
        """Build the value-cell tooltip from tie, raw-error, and staleness information."""
        lines: list[str] = []

        tie_tooltip = self._port.tie_tooltip_for(component, parameter_name)
        if tie_tooltip is not None:
            lines.append(tie_tooltip)

        error_value = self._parameter_error_value(param_obj)
        if error_value is not None:
            lines.append(
                QCoreApplication.translate("RegionDetailPanel", "Uncertainty: {error}").format(
                    error=error_value
                )
            )

        if is_stale and error_value is not None:
            lines.append(
                QCoreApplication.translate(
                    "RegionDetailPanel",
                    "This is the uncertainty from the previous fit; it no longer applies to "
                    "the current value because this component needs re-optimization.",
                )
            )

        return "\n".join(lines)

    def _clear_line_parameter_columns(self, item: QTreeWidgetItem) -> None:
        """Render a placeholder in parameter cells that line rows do not use."""
        for parameter_column in self._columns.parameter_columns:
            if parameter_column.value_column != self._columns.redshift_column:
                item.setText(parameter_column.value_column, _EMPTY_CELL_PLACEHOLDER)
                item.setData(parameter_column.value_column, ROLE_EDIT_KIND, TreeCellEditKind.NONE)

    def refresh_line_analysis_half_width(
        self, item: QTreeWidgetItem, lines: tuple[AbsorptionLine, ...]
    ) -> None:
        """Refresh the scientific half-width cell for a rendered line group."""
        self._set_line_analysis_half_width(item, lines)

    def _set_line_analysis_half_width(
        self, item: QTreeWidgetItem, lines: tuple[AbsorptionLine, ...]
    ) -> None:
        """Render a common value or Mixed for a line/multiplet row."""
        values = tuple(line.window_kms for line in lines)
        common = (
            values[0]
            if values and all(math.isclose(values[0], value) for value in values)
            else None
        )
        column = self._columns.analysis_half_width_column
        if common is None:
            item.setText(column, QCoreApplication.translate("RegionDetailPanel", "Mixed"))
            item.setData(column, ROLE_RAW_VALUE, None)
        else:
            item.setText(column, f"±{common:g}")
            item.setData(column, ROLE_RAW_VALUE, float(common))
        item.setData(column, ROLE_EDIT_KIND, TreeCellEditKind.LINE_ANALYSIS_HALF_WIDTH)

    def _apply_line_row_style(self, item: QTreeWidgetItem) -> None:
        """Apply non-editable bold styling to a line row."""
        font = item.font(self._columns.id_column)
        font.setBold(True)
        background_brush = QColor(Colors.BACKGROUND_WIDGET)
        for column in range(self._columns.column_count):
            item.setFont(column, font)
            item.setBackground(column, background_brush)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

    @staticmethod
    def _observed_wavelength(component: AbsorberComponent) -> float:
        """Return the observed wavelength for a component."""
        return component.wavelength * (
            1.0 + OptimizeTreeRowRenderer._parameter_value(component, "redshift")
        )

    @staticmethod
    def _parameter_value(
        component: AbsorberComponent, param: str, *, default: float = 0.0
    ) -> float:
        """Return a numeric component parameter value."""
        if param not in component.parameters:
            return default
        return float(component.parameters[param].value)

    @staticmethod
    def _parameter_error_value(param: Parameter | None) -> float | None:
        """Return a finite positive error value, when available."""
        if param is None:
            return None
        error_value = float(param.error)
        if not math.isfinite(error_value) or error_value <= 0.0:
            return None
        return error_value
