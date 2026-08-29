"""Parameter controls component for AbsorberEditor.

This module handles all parameter input widgets, validation, and real-time feedback
for absorption line components.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
)

from chappy.core.components.absorber import AbsorberComponent
from chappy.core.validation_constants import PARAM_VALIDATION

logger = logging.getLogger(__name__)


class AbsorberParameterControls(QObject):
    """Handle parameter input widgets and validation for absorber components.

    Handles creation and management of:
    - Basic parameter controls (column density, b-parameter, redshift)
    - Atomic data section (transition selection, oscillator strength, gamma)
    - Component controls (enabled checkbox, duplicate button)
    - Real-time parameter validation and feedback

    Signals:
        parameter_changed: Emitted when parameter value changes
    """

    # Signals for parameter changes
    parameter_changed = Signal(AbsorberComponent, str, float)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize parameter controls.

        Args:
            parent: Parent QObject
        """
        super().__init__(parent)
        self._controls: dict[str, QDoubleSpinBox | QCheckBox] = {}

        logger.debug("AbsorberParameterControls initialized")

    def _create_column_density_controls(
        self, absorber: AbsorberComponent, controls: dict[str, QDoubleSpinBox | QCheckBox]
    ) -> QHBoxLayout:
        """Create column density parameter controls.

        Args:
            absorber: Absorber component
            controls: Controls dictionary to populate

        Returns:
            Column density controls layout
        """
        column_layout = QHBoxLayout()

        column_density_spin = QDoubleSpinBox()
        column_density_spin.setRange(10.0, 22.0)
        column_density_spin.setSuffix(" log(cm⁻²)")
        column_density_spin.setDecimals(2)
        column_density_spin.setValue(absorber.parameters["column_density"].value)
        column_density_spin.valueChanged.connect(
            lambda v: self._on_parameter_changed(absorber, "column_density", v)
        )
        controls["column_density_spin"] = column_density_spin
        logger.debug("Connected column_density_spin valueChanged signal for %s", absorber.name)
        column_layout.addWidget(column_density_spin)

        column_density_fixed = QCheckBox("Fixed")
        column_density_fixed.setChecked(absorber.parameters["column_density"].fixed)
        controls["column_density_fixed"] = column_density_fixed
        column_layout.addWidget(column_density_fixed)

        return column_layout

    def _create_b_parameter_controls(
        self, absorber: AbsorberComponent, controls: dict[str, QDoubleSpinBox | QCheckBox]
    ) -> QHBoxLayout:
        """Create b parameter controls.

        Args:
            absorber: Absorber component
            controls: Controls dictionary to populate

        Returns:
            B parameter controls layout
        """
        b_layout = QHBoxLayout()

        b_parameter_spin = QDoubleSpinBox()
        b_parameter_spin.setRange(1.0, 1000.0)
        b_parameter_spin.setSuffix(" km/s")
        b_parameter_spin.setDecimals(1)
        b_parameter_spin.setValue(absorber.parameters["b_parameter"].value)
        b_parameter_spin.valueChanged.connect(
            lambda v: self._on_parameter_changed(absorber, "b_parameter", v)
        )
        controls["b_parameter_spin"] = b_parameter_spin
        b_layout.addWidget(b_parameter_spin)

        b_parameter_fixed = QCheckBox("Fixed")
        b_parameter_fixed.setChecked(absorber.parameters["b_parameter"].fixed)
        controls["b_parameter_fixed"] = b_parameter_fixed
        b_layout.addWidget(b_parameter_fixed)

        return b_layout

    def _create_redshift_controls(
        self, absorber: AbsorberComponent, controls: dict[str, QDoubleSpinBox | QCheckBox]
    ) -> QHBoxLayout:
        """Create redshift parameter controls.

        Args:
            absorber: Absorber component
            controls: Controls dictionary to populate

        Returns:
            Redshift controls layout
        """
        redshift_layout = QHBoxLayout()

        redshift_spin = QDoubleSpinBox()
        redshift_spin.setRange(-0.1, 10.0)
        redshift_spin.setDecimals(6)
        redshift_spin.setValue(absorber.parameters["redshift"].value)
        redshift_spin.valueChanged.connect(
            lambda v: self._on_parameter_changed(absorber, "redshift", v)
        )
        controls["redshift_spin"] = redshift_spin
        redshift_layout.addWidget(redshift_spin)

        redshift_fixed = QCheckBox("Fixed")
        redshift_fixed.setChecked(absorber.parameters["redshift"].fixed)
        controls["redshift_fixed"] = redshift_fixed
        redshift_layout.addWidget(redshift_fixed)

        return redshift_layout

    def validate_parameter_ranges(self, param_name: str, value: float) -> bool:
        """Validate parameter value is within acceptable range.

        Args:
            param_name: Name of the parameter
            value: Value to validate

        Returns:
            True if value is valid, False otherwise
        """
        if param_name == "column_density":
            return (
                PARAM_VALIDATION.COLUMN_DENSITY_MIN <= value <= PARAM_VALIDATION.COLUMN_DENSITY_MAX
            )
        if param_name == "b_parameter":
            return PARAM_VALIDATION.B_PARAMETER_MIN <= value <= PARAM_VALIDATION.B_PARAMETER_MAX
        if param_name == "redshift":
            return PARAM_VALIDATION.REDSHIFT_MIN <= value <= PARAM_VALIDATION.REDSHIFT_MAX

        return True

    def _on_parameter_changed(
        self, absorber: AbsorberComponent, param_name: str, value: float
    ) -> None:
        """Handle parameter value change.

        Args:
            absorber: Absorber component
            param_name: Name of changed parameter
            value: New parameter value
        """
        logger.info(
            "🎛️ PARAM_CONTROLS: Parameter change triggered from UI control: %s.%s = %s",
            absorber.name,
            param_name,
            value,
        )

        if self.validate_parameter_ranges(param_name, value):
            logger.info(
                "📤 PARAM_CONTROLS: Emitting parameter_changed signal: absorber=%s, param=%s, value=%s",
                absorber.name,
                param_name,
                value,
            )
            self.parameter_changed.emit(absorber, param_name, value)
            logger.debug(
                "Parameter changed for absorber",
                extra={"param_name": param_name, "value": value, "absorber_name": absorber.name},
            )
        else:
            logger.warning(
                "Invalid value for parameter", extra={"value": value, "param_name": param_name}
            )

    def set_current_absorber(self, absorber: AbsorberComponent | None) -> None:
        """Set the current absorber for parameter display.

        Args:
            absorber: Absorber component to display or None to clear
        """
        logger.info(
            "🎯 PARAM_CONTROLS: set_current_absorber called with: %s",
            absorber.name if absorber else "None",
        )

        if absorber:
            # Populate the parameter section with controls for this absorber
            self._populate_parameter_section(absorber)
        else:
            # Clear the parameter section
            self._clear_parameter_section()
            # Show placeholder
            self._placeholder_label = QLabel("No absorber selected")
            self._params_layout.addRow(self._placeholder_label)

    def create_parameter_section(self) -> QGroupBox:
        """Create the main parameter section widget.

        Returns:
            QGroupBox containing all parameter controls
        """
        # Create the main parameter controls widget
        self._params_group = QGroupBox("Parameters")
        self._params_layout = QFormLayout()
        self._params_group.setLayout(self._params_layout)

        # Initially show placeholder
        self._placeholder_label = QLabel("No absorber selected")
        self._params_layout.addRow(self._placeholder_label)

        logger.debug("Parameter section created")
        return self._params_group

    def _clear_parameter_section(self) -> None:
        """Clear all widgets from the parameter section."""
        # Remove all widgets from layout
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                widget.deleteLater()

    def _populate_parameter_section(self, absorber: AbsorberComponent) -> None:
        """Populate parameter section with controls for the given absorber.

        Args:
            absorber: Absorber component to create controls for
        """
        logger.info("🔧 PARAM_CONTROLS: Populating parameter section for %s", absorber.name)

        # Clear existing controls
        self._clear_parameter_section()

        # Reset controls dictionary
        self._controls = {}

        # Add basic parameter controls
        self._params_layout.addRow(
            "Column Density:", self._create_column_density_controls(absorber, self._controls)
        )
        self._params_layout.addRow(
            "Doppler parameter:", self._create_b_parameter_controls(absorber, self._controls)
        )
        self._params_layout.addRow(
            "Redshift:", self._create_redshift_controls(absorber, self._controls)
        )
