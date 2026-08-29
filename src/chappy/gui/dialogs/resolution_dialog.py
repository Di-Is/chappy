"""Spectral resolution settings dialog implementation (SCR-DIA-RES)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QLocale, QSettings, QSize, Qt, Signal, Slot
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chappy.core.resolution import (
    RESOLUTION_CONSTRAINTS,
    SETTINGS_RESOLUTION_ENABLED_KEY,
    SETTINGS_RESOLUTION_VALUE_KEY,
    ResolutionState,
)
from chappy.gui.dialog_sizing import enforce_translated_minimum_size
from chappy.gui.theme import Fonts, apply_action_row_sizing, apply_button_variant
from chappy.gui.visual_tokens import DialogMetrics
from chappy.i18n import LanguageSwitcher, get_language_switcher

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True)
class _ValidationResult:
    """Container describing the outcome of validating the resolution field."""

    valid: bool
    message: str = ""


class ResolutionDialog(QDialog):
    """Modal dialog allowing the user to configure spectral resolution (R)."""

    resolution_applied = Signal(float, bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
        initial_state: ResolutionState | None = None,
        status_callback: Callable[[str, str], None] | None = None,
        language_switcher: LanguageSwitcher | None = None,
    ) -> None:
        super().__init__(parent)

        self._settings = settings or QSettings()
        self._locale = QLocale()
        self._status_callback = status_callback
        self._constraints = RESOLUTION_CONSTRAINTS
        self._min = float(self._constraints["min"])
        self._max = float(self._constraints["max"])
        self._default = float(self._constraints["default"])
        self._step = float(self._constraints["step"])
        self._decimals = int(self._constraints["decimals"])
        self._language_switcher: LanguageSwitcher = language_switcher or get_language_switcher()

        self._initial_state = initial_state or self._load_state_from_settings()
        self._current_state = ResolutionState(
            value=self._initial_state.value, enabled=self._initial_state.enabled
        )

        self._spinbox: QDoubleSpinBox | None = None
        self._spin_line_edit: QLineEdit | None = None
        self._description_label: QLabel | None = None
        self._field_label: QLabel | None = None
        self._unit_label: QLabel | None = None
        self._error_label: QLabel | None = None
        self._range_label: QLabel | None = None
        self._checkbox: QCheckBox | None = None
        self._ok_button: QPushButton | None = None
        self._cancel_button: QPushButton | None = None

        self._setup_ui()
        # Fail fast if the expected widgets were not created correctly.
        self._require_spinbox()
        self._require_checkbox()
        self._require_error_label()
        self._require_ok_button()
        self._apply_state(self._current_state)
        self._apply_translations()
        self._validate_resolution_field()
        self._language_switcher.language_changed.connect(self._on_language_changed)

    @property
    def resolution_value(self) -> float:
        """Return the currently selected resolution (R)."""
        spinbox = self._require_spinbox()
        return float(spinbox.value())

    @property
    def resolution_enabled(self) -> bool:
        """Return whether instrumental resolution is enabled."""
        checkbox = self._require_checkbox()
        return bool(checkbox.isChecked())

    def _setup_ui(self) -> None:
        self.setModal(True)
        self.setProperty("role", "dialog")
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        self._description_label = QLabel(self)
        self._description_label.setWordWrap(True)
        self._description_label.setObjectName("resolutionDescription")
        main_layout.addWidget(self._description_label)

        form_container = QWidget(self)
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)

        field_row = QWidget(form_container)
        field_layout = QHBoxLayout(field_row)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(12)

        self._field_label = QLabel(field_row)
        self._field_label.setObjectName("resolutionLabel")
        self._field_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._field_label.setMinimumWidth(170)
        field_layout.addWidget(self._field_label)

        self._spinbox = QDoubleSpinBox(field_row)
        self._spinbox.setObjectName("resolutionSpin")
        self._spinbox.setDecimals(self._decimals)
        self._spinbox.setRange(self._min, self._max)
        self._spinbox.setSingleStep(self._step)
        self._spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        self._spinbox.setAccelerated(True)
        self._spinbox.setKeyboardTracking(False)
        self._spinbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._spinbox.setMaximumWidth(160)
        field_layout.addWidget(self._spinbox)

        self._unit_label = QLabel(field_row)
        self._unit_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._unit_label.setObjectName("resolutionUnitLabel")
        field_layout.addWidget(self._unit_label)
        field_layout.addStretch()

        form_layout.addWidget(field_row)

        validator = QDoubleValidator(self._min, self._max, self._decimals, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        validator.setLocale(self._locale)
        line_edit = self._spinbox.lineEdit()
        if line_edit is not None:
            line_edit.setValidator(validator)
            line_edit.textChanged.connect(self._handle_resolution_text_changed)
            self._spin_line_edit = line_edit

        self._spinbox.valueChanged.connect(self._handle_resolution_value_changed)

        self._range_label = QLabel("", form_container)
        self._range_label.setObjectName("resolutionRangeLabel")
        self._range_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form_layout.addWidget(self._range_label)

        self._error_label = QLabel("", form_container)
        self._error_label.setObjectName("resolutionErrorLabel")
        self._error_label.setVisible(False)
        self._error_label.setStyleSheet(f"color: #d93025; font-size: {Fonts.SIZE_NORMAL};")
        self._error_label.setProperty("aria-live", "assertive")
        form_layout.addWidget(self._error_label)

        main_layout.addWidget(form_container)

        self._checkbox = QCheckBox(self)
        self._checkbox.setObjectName("applyResolutionCheckbox")
        main_layout.addWidget(self._checkbox)

        main_layout.addWidget(self._create_separator())

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(12)
        button_row.addStretch()

        self._cancel_button = QPushButton(self)
        self._cancel_button.setObjectName("cancelButton")
        self._cancel_button.clicked.connect(self.reject)
        self._cancel_button.setAutoDefault(False)
        apply_button_variant(self._cancel_button, "secondary")
        button_row.addWidget(self._cancel_button)

        self._ok_button = QPushButton(self)
        self._ok_button.setObjectName("okButton")
        self._ok_button.setDefault(True)
        self._ok_button.clicked.connect(self._handle_accept_clicked)
        apply_button_variant(self._ok_button, "primary")
        button_row.addWidget(self._ok_button)

        apply_action_row_sizing(self._cancel_button, self._ok_button)

        main_layout.addLayout(button_row)

        self._spinbox.setFocus(Qt.FocusReason.OtherFocusReason)
        self._spinbox.selectAll()

    def _create_separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #e0e0e0;")
        return line

    def _apply_translations(self) -> None:
        """Apply i18n resources to all UI elements."""
        title = self.tr("Resolution Settings")
        self.setWindowTitle(title)
        self.setAccessibleName(title)

        description_text = self.tr(
            "Configure the spectral resolution R = λ/Δλ for the current spectrum."
        )

        if self._description_label is not None:
            self._description_label.setText(description_text)
            self._description_label.setAccessibleDescription(description_text)

        if self._field_label is not None and self._spinbox is not None:
            label_text = self.tr("Spectral Resolution R:")
            self._field_label.setText(label_text)
            self._field_label.setBuddy(self._spinbox)

        if self._unit_label is not None:
            unit_text = self.tr("(dimensionless)")
            self._unit_label.setText(unit_text)

        formula_tip = self.tr("Spectral Resolution R = λ/Δλ")
        input_name = self.tr("Resolution value input")
        if self._spinbox is not None:
            self._spinbox.setToolTip(formula_tip)
            self._spinbox.setWhatsThis(description_text)
            self._spinbox.setAccessibleName(input_name)

        if self._spin_line_edit is not None:
            self._spin_line_edit.setToolTip(formula_tip)
            self._spin_line_edit.setAccessibleName(input_name)

        if self._range_label is not None:
            range_text = self._format_range_text()
            self._range_label.setText(range_text)
            self._range_label.setAccessibleDescription(range_text)
            range_accessible = self.tr("Resolution range hint")
            self._range_label.setAccessibleName(range_accessible)

        if self._checkbox is not None:
            toggle_label = self.tr("Apply instrumental resolution")
            self._checkbox.setText(toggle_label)
            self._checkbox.setAccessibleName(toggle_label)
            self._checkbox.setToolTip(
                self.tr("Include instrumental resolution effects in the model")
            )

        if self._cancel_button is not None:
            cancel_text = self.tr("Cancel")
            self._cancel_button.setText(cancel_text)
            self._cancel_button.setAccessibleName(cancel_text)

        if self._ok_button is not None:
            ok_text = self.tr("OK")
            self._ok_button.setText(ok_text)
            self._ok_button.setAccessibleName(ok_text)

        enforce_translated_minimum_size(
            self, floor=QSize(DialogMetrics.MIN_WIDTH_DEFAULT, DialogMetrics.MIN_HEIGHT_DEFAULT)
        )

    @Slot(str)
    def _on_language_changed(self, _code: str) -> None:
        """React to runtime language updates."""
        self._apply_translations()
        self._validate_resolution_field()

    @Slot(str)
    def _handle_resolution_text_changed(self, _text: str) -> None:
        self._validate_resolution_field()

    @Slot(float)
    def _handle_resolution_value_changed(self, _value: float) -> None:
        self._validate_resolution_field()

    @Slot()
    def _handle_accept_clicked(self) -> None:
        if not self._validate_resolution_field().valid:
            return

        self._current_state = ResolutionState(
            value=self.resolution_value, enabled=self.resolution_enabled
        )
        self._write_state_to_settings(self._current_state)
        self.resolution_applied.emit(self._current_state.value, self._current_state.enabled)
        success_template = self.tr("Applied resolution R={R}")
        self._show_status(
            success_template.format(R=self._format_number(self._current_state.value))
        )
        self.accept()

    def _validate_resolution_field(self) -> _ValidationResult:
        spinbox = self._require_spinbox()
        self._require_error_label()

        line_edit = spinbox.lineEdit()
        text = line_edit.text().strip() if line_edit is not None else spinbox.text().strip()

        invalid_number = self.tr("Please enter a valid number")

        if not text:
            self._set_field_invalid(invalid_number)
            return _ValidationResult(valid=False, message=invalid_number)

        value, ok = self._locale.toDouble(text)
        if not ok:
            self._set_field_invalid(invalid_number)
            return _ValidationResult(valid=False, message=invalid_number)

        if value < self._min:
            min_template = self.tr("Please enter a value of {min} or greater")
            message = min_template.format(min=self._format_number(self._min))
            self._set_field_invalid(message)
            return _ValidationResult(valid=False, message=message)

        if value > self._max:
            max_template = self.tr("Please enter a value of {max:,} or less")
            message = max_template.format(max=self._format_number(self._max))
            self._set_field_invalid(message)
            return _ValidationResult(valid=False, message=message)

        self._set_field_valid()
        return _ValidationResult(valid=True)

    def _set_field_invalid(self, message: str) -> None:
        spinbox = self._require_spinbox()
        error_label = self._require_error_label()
        ok_button = self._require_ok_button()

        error_label.setText(message)
        error_label.setAccessibleDescription(message)
        error_label.setVisible(True)
        spinbox.setStyleSheet(
            "QDoubleSpinBox { border: 1px solid #d93025; background-color: rgba(217,48,37,0.05); }"
        )
        spinbox.setAccessibleDescription(message)
        ok_button.setEnabled(False)

    def _set_field_valid(self) -> None:
        spinbox = self._require_spinbox()
        error_label = self._require_error_label()
        ok_button = self._require_ok_button()

        error_label.setVisible(False)
        error_label.setText("")
        error_label.setAccessibleDescription("")
        spinbox.setStyleSheet("")
        spinbox.setAccessibleDescription("")
        ok_button.setEnabled(True)

    def _apply_state(self, state: ResolutionState) -> None:
        spinbox = self._require_spinbox()
        checkbox = self._require_checkbox()

        spinbox.blockSignals(True)
        spinbox.setValue(state.value)
        spinbox.blockSignals(False)

        checkbox.blockSignals(True)
        checkbox.setChecked(state.enabled)
        checkbox.blockSignals(False)

    def _require_spinbox(self) -> QDoubleSpinBox:
        if self._spinbox is None:
            msg = "Resolution spinbox was not initialized; UI setup did not complete successfully."
            raise RuntimeError(msg)
        return self._spinbox

    def _require_checkbox(self) -> QCheckBox:
        if self._checkbox is None:
            msg = "Resolution enable checkbox was not initialized; UI setup did not complete successfully."
            raise RuntimeError(msg)
        return self._checkbox

    def _require_error_label(self) -> QLabel:
        if self._error_label is None:
            msg = "Resolution error label was not initialized; UI setup did not complete successfully."
            raise RuntimeError(msg)
        return self._error_label

    def _require_ok_button(self) -> QPushButton:
        if self._ok_button is None:
            msg = "Resolution dialog OK button was not initialized; UI setup did not complete successfully."
            raise RuntimeError(msg)
        return self._ok_button

    def _load_state_from_settings(self) -> ResolutionState:
        value: object = self._settings.value(SETTINGS_RESOLUTION_VALUE_KEY, None)
        enabled: object = self._settings.value(SETTINGS_RESOLUTION_ENABLED_KEY, None)

        if value is None:
            value_float = self._default
        elif isinstance(value, str | int | float):
            try:
                value_float = float(value)
            except ValueError:
                value_float = self._default
        else:
            value_float = self._default

        if value_float < self._min or value_float > self._max:
            value_float = self._default

        enabled_bool: bool
        if isinstance(enabled, bool):
            enabled_bool = enabled
        elif isinstance(enabled, str):
            enabled_bool = enabled.lower() in {"true", "1", "yes"}
        else:
            enabled_bool = True

        return ResolutionState(value=value_float, enabled=enabled_bool)

    def _write_state_to_settings(self, state: ResolutionState) -> None:
        self._settings.setValue(SETTINGS_RESOLUTION_VALUE_KEY, state.value)
        self._settings.setValue(SETTINGS_RESOLUTION_ENABLED_KEY, state.enabled)
        self._settings.sync()

    def _format_number(self, value: float) -> str:
        decimals = self._decimals
        if math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-9):
            decimals = 0
        formatted = self._locale.toString(value, "f", decimals)
        if not isinstance(formatted, str):
            msg = "Expected QLocale.toString() to return str"
            raise TypeError(msg)
        return formatted

    def _format_range_text(self) -> str:
        template = self.tr("Range: {min} - {max:,}")
        return template.format(min=self._format_number(self._min), max=self._max)

    def _show_status(self, message: str, level: str = "success") -> None:
        if self._status_callback:
            self._status_callback(message, level)


__all__ = ["ResolutionDialog"]
