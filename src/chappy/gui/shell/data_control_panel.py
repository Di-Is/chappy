"""Data display control panel located at the bottom of the main window."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, override

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QDoubleValidator, QKeyEvent, QValidator
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from chappy.gui.theme import (
    Colors,
    Fonts,
    apply_button_variant,
    create_styled_menu,
    toolbar_tool_button_style,
)
from chappy.gui.visual_tokens import LayoutMetrics

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtGui import QAction


_FieldLabelKind = Literal["min", "max"]


@dataclass
class RangeValues:
    """Stores the numeric range values displayed in the control panel."""

    wavelength_min: float
    wavelength_max: float
    flux_min: float
    flux_max: float


def _validate_range_values(values: RangeValues) -> None:
    """Validate range values before they become panel state.

    Args:
        values: Range values to validate.

    Raises:
        ValueError: If a value is not finite or a range is not ordered.
    """
    numeric_values = (
        values.wavelength_min,
        values.wavelength_max,
        values.flux_min,
        values.flux_max,
    )
    if not all(math.isfinite(value) for value in numeric_values):
        msg = "Range values must be finite."
        raise ValueError(msg)
    if values.wavelength_min >= values.wavelength_max:
        msg = "Wavelength range must satisfy min < max."
        raise ValueError(msg)
    if values.flux_min >= values.flux_max:
        msg = "Flux range must satisfy min < max."
        raise ValueError(msg)


class _NumericFieldController(QObject):
    """Handles focus state and ESC revert for a numeric QLineEdit."""

    value_applied = Signal(float)
    invalid_input_rejected = Signal()

    def __init__(
        self,
        field: QLineEdit,
        default: float | None,
        *,
        validator: QValidator,
        to_value: Callable[[str], float],
        format_value: Callable[[float], str],
    ) -> None:
        """Configure validation and formatting for a numeric field.

        Args:
            field: Target line edit widget.
            default: Initial numeric value to display, or None for pending state.
            validator: Qt validator that constrains input.
            to_value: Converter from text to float value.
            format_value: Formatter that produces display text from a float value.
        """
        super().__init__(field)
        self._field = field
        self._to_value = to_value
        self._format_value = format_value
        self._previous_text = "" if default is None else format_value(default)
        self._field.installEventFilter(self)
        self._validator = validator
        self._field.setValidator(self._validator)
        self._field.setText(self._previous_text)

    def set_value(self, value: float) -> None:
        text = self._format_value(value)
        self._previous_text = text
        self._field.blockSignals(True)
        self._field.setText(text)
        self._field.blockSignals(False)

    def clear(self) -> None:
        """Clear the field and reset the accepted text to pending."""
        self._previous_text = ""
        self._field.blockSignals(True)
        self._field.clear()
        self._field.blockSignals(False)

    def set_enabled(self, enabled: bool) -> None:
        self._field.setEnabled(enabled)

    def set_tooltip(self, tooltip: str | None) -> None:
        self._field.setToolTip(tooltip or "")

    @property
    def field(self) -> QLineEdit:
        return self._field

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._field:
            if isinstance(event, QKeyEvent):
                if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                    self._apply_current_text()
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self._field.setText(self._previous_text)
                    return True
            if event.type() == QEvent.Type.FocusIn:
                self._previous_text = self._field.text()
            if event.type() == QEvent.Type.FocusOut:
                self._apply_current_text()
        return super().eventFilter(obj, event)

    def _apply_current_text(self) -> None:
        if not self._field.hasAcceptableInput():
            self._field.setText(self._previous_text)
            self.invalid_input_rejected.emit()
            return
        text = self._field.text()
        if text == self._previous_text:
            return
        try:
            value = self._to_value(text)
        except ValueError:
            self._field.setText(self._previous_text)
            self.invalid_input_rejected.emit()
            return
        self._previous_text = text
        self.value_applied.emit(value)


class DataControlPanel(QFrame):
    """Panel for wavelength/flux range entry and reset controls."""

    wavelength_range_applied = Signal(float, float)
    flux_range_applied = Signal(float, float)
    reset_requested = Signal()
    auto_adjust_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Set up widgets and layout for the control panel."""
        super().__init__(parent)
        self.setObjectName("dataControlPanel")
        self.setMinimumHeight(LayoutMetrics.DATACONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # No descendant QWidget rule here: widget-level sheets outrank the
        # application sheet, so it would wipe QPushButton[variant=...] fills.
        self.setStyleSheet(
            "#dataControlPanel {"
            f" background-color: {Colors.BACKGROUND_PANEL};"
            f" border-top: 1px solid {Colors.BORDER_DEFAULT};"
            "}"
        )

        self._values: RangeValues | None = None
        self._wavelength_min_field: QLineEdit | None = None
        self._wavelength_max_field: QLineEdit | None = None
        self._wavelength_header_label: QLabel | None = None
        self._flux_header_label: QLabel | None = None
        self._reset_button: QPushButton | None = None
        self._auto_adjust_button: QPushButton | None = None
        self._display_menu_button: QToolButton | None = None
        self._min_labels: list[QLabel] = []
        self._max_labels: list[QLabel] = []

        # Build layout
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(16, 6, 16, 6)
        root_layout.setSpacing(12)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        fields_container = QWidget(self)
        fields_layout = QHBoxLayout(fields_container)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(12)

        self._wavelength_group = self._build_wavelength_inputs()
        self._flux_group = self._build_flux_inputs()
        self._button_group = self._build_button_group()

        fields_layout.addWidget(self._wavelength_group)
        fields_layout.addWidget(
            self._create_separator("dataControlPanel_separator_wavelength_flux")
        )
        fields_layout.addWidget(self._flux_group)
        fields_layout.addStretch(1)

        root_layout.addWidget(fields_container, stretch=1)
        root_layout.addWidget(self._button_group)

        self._set_range_controls_enabled(False)
        self._apply_translations()

    @override
    def changeEvent(self, event: QEvent) -> None:
        """Refresh translated labels when Qt language changes."""
        if event.type() == QEvent.Type.LanguageChange:
            self._apply_translations()
        super().changeEvent(event)

    def update_ranges(self, values: RangeValues) -> None:
        """Update UI to match latest range values without firing signals."""
        _validate_range_values(values)
        self._values = values
        self._set_range_controls_enabled(True)
        self._wavelength_min_ctrl.set_value(values.wavelength_min)
        self._wavelength_max_ctrl.set_value(values.wavelength_max)
        self._flux_min_ctrl.set_value(values.flux_min)
        self._flux_max_ctrl.set_value(values.flux_max)

    def clear_ranges(self) -> None:
        """Return range controls to the pending no-spectrum state."""
        self._values = None
        self._set_range_controls_enabled(False)
        self._wavelength_min_ctrl.clear()
        self._wavelength_max_ctrl.clear()
        self._flux_min_ctrl.clear()
        self._flux_max_ctrl.clear()

    def set_wavelength_fields_enabled(self, enabled: bool) -> None:
        """Enable or disable direct editing of the wavelength range."""
        if self._wavelength_min_field is not None:
            self._wavelength_min_field.setEnabled(enabled)
        if self._wavelength_max_field is not None:
            self._wavelength_max_field.setEnabled(enabled)

    def _set_range_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable wavelength and flux range controls."""
        self._wavelength_min_ctrl.set_enabled(enabled)
        self._wavelength_max_ctrl.set_enabled(enabled)
        self._flux_min_ctrl.set_enabled(enabled)
        self._flux_max_ctrl.set_enabled(enabled)
        if self._reset_button is not None:
            self._reset_button.setEnabled(enabled)
        if self._auto_adjust_button is not None:
            self._auto_adjust_button.setEnabled(enabled)

    # --- Builders -----------------------------------------------------
    def _build_wavelength_inputs(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("dataControlPanel_wavelengthGroup")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        header = QLabel()
        header.setObjectName("dataControlPanel_wavelengthHeaderLabel")
        self._wavelength_header_label = header
        header.setStyleSheet(
            f"font-size: {Fonts.SIZE_NORMAL}; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
        )
        layout.addWidget(header)

        min_field = self._create_numeric_field()
        max_field = self._create_numeric_field()
        min_field.setObjectName("dataControlPanel_wavelengthMinField")
        max_field.setObjectName("dataControlPanel_wavelengthMaxField")
        self._wavelength_min_field = min_field
        self._wavelength_max_field = max_field

        layout.addWidget(
            self._build_field_row(
                "min", min_field, label_object_name="dataControlPanel_wavelengthMinLabel"
            )
        )
        layout.addWidget(
            self._build_field_row(
                "max", max_field, label_object_name="dataControlPanel_wavelengthMaxLabel"
            )
        )

        self._wavelength_min_ctrl = _NumericFieldController(
            min_field,
            None,
            validator=QDoubleValidator(bottom=-1e9, top=1e9, decimals=2, parent=self),
            to_value=float,
            format_value=lambda value: f"{value:.2f}",
        )
        self._wavelength_min_ctrl.value_applied.connect(self._apply_wavelength_min)
        self._wavelength_min_ctrl.invalid_input_rejected.connect(self._show_invalid_feedback)

        self._wavelength_max_ctrl = _NumericFieldController(
            max_field,
            None,
            validator=QDoubleValidator(bottom=-1e9, top=1e9, decimals=2, parent=self),
            to_value=float,
            format_value=lambda value: f"{value:.2f}",
        )
        self._wavelength_max_ctrl.value_applied.connect(self._apply_wavelength_max)
        self._wavelength_max_ctrl.invalid_input_rejected.connect(self._show_invalid_feedback)

        return container

    def _build_flux_inputs(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("dataControlPanel_fluxGroup")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        header = QLabel()
        header.setObjectName("dataControlPanel_fluxHeaderLabel")
        self._flux_header_label = header
        header.setStyleSheet(
            f"font-size: {Fonts.SIZE_NORMAL}; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
        )
        layout.addWidget(header)

        min_field = self._create_numeric_field()
        max_field = self._create_numeric_field()
        min_field.setObjectName("dataControlPanel_fluxMinField")
        max_field.setObjectName("dataControlPanel_fluxMaxField")

        layout.addWidget(
            self._build_field_row(
                "min", min_field, label_object_name="dataControlPanel_fluxMinLabel"
            )
        )
        layout.addWidget(
            self._build_field_row(
                "max", max_field, label_object_name="dataControlPanel_fluxMaxLabel"
            )
        )

        self._flux_min_ctrl = _NumericFieldController(
            min_field,
            None,
            validator=QDoubleValidator(bottom=-1e9, top=1e9, decimals=2, parent=self),
            to_value=float,
            format_value=lambda value: f"{value:.2f}",
        )
        self._flux_min_ctrl.value_applied.connect(self._apply_flux_min)
        self._flux_min_ctrl.invalid_input_rejected.connect(self._show_invalid_feedback)

        self._flux_max_ctrl = _NumericFieldController(
            max_field,
            None,
            validator=QDoubleValidator(bottom=-1e9, top=1e9, decimals=2, parent=self),
            to_value=float,
            format_value=lambda value: f"{value:.2f}",
        )
        self._flux_max_ctrl.value_applied.connect(self._apply_flux_max)
        self._flux_max_ctrl.invalid_input_rejected.connect(self._show_invalid_feedback)

        return container

    def _build_field_row(
        self,
        label_kind: _FieldLabelKind | None,
        field: QLineEdit,
        *,
        literal: str | None = None,
        label_object_name: str | None = None,
    ) -> QWidget:
        column = QWidget(self)
        layout = QHBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel()
        if label_object_name:
            label.setObjectName(label_object_name)
        if label_kind is None:
            if literal is None:
                msg = "literal text required when label_kind is None"
                raise ValueError(msg)
            label.setText(literal)
        else:
            self._register_field_label(label, label_kind)
        label.setFixedWidth(32)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_NORMAL}; font-weight: 500;"
        )
        layout.addWidget(label)
        layout.addWidget(field)

        return column

    def _register_field_label(self, label: QLabel, label_kind: _FieldLabelKind) -> None:
        """Track a field label that must be refreshed on language changes."""
        if label_kind == "min":
            self._min_labels.append(label)
            return
        self._max_labels.append(label)

    def attach_display_menu(self, actions: tuple[QAction, ...]) -> None:
        """Attach display toggle actions as a Display menu button before Reset View.

        Args:
            actions: Checkable display actions rendered in menu order.
        """
        button = QToolButton(self)
        button.setObjectName("displayMenuButton")
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(toolbar_tool_button_style())
        menu = create_styled_menu(button)
        for action in actions:
            menu.addAction(action)
            # A popup menu is its own window, so its shortcuts only reach the main
            # window while the action also belongs to a widget inside it.
            self.addAction(action)
        button.setMenu(menu)

        self._display_menu_button = button
        reset_button = self._reset_button
        insert_index = 0 if reset_button is None else self._button_layout.indexOf(reset_button)
        self._button_layout.insertWidget(insert_index, button)
        self._apply_translations()

    def _build_button_group(self) -> QWidget:
        container = QWidget(self)
        container.setObjectName("dataControlPanel_buttonGroup")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._button_layout = layout

        reset_btn = QPushButton()
        reset_btn.setObjectName("resetViewButton")
        reset_btn.clicked.connect(self._emit_reset)
        apply_button_variant(reset_btn, "secondary")
        layout.addWidget(reset_btn)
        self._reset_button = reset_btn

        auto_btn = QPushButton()
        auto_btn.setObjectName("autoAdjustButton")
        auto_btn.clicked.connect(self.auto_adjust_requested.emit)
        apply_button_variant(auto_btn, "secondary")
        layout.addWidget(auto_btn)
        self._auto_adjust_button = auto_btn

        return container

    def _emit_reset(self) -> None:
        self.reset_requested.emit()

    def _create_numeric_field(self, *, placeholder: str = "") -> QLineEdit:
        field = QLineEdit(self)
        field.setAlignment(Qt.AlignmentFlag.AlignRight)
        field.setMinimumWidth(LayoutMetrics.NUMERIC_INPUT_MIN_WIDTH)
        field.setMaximumWidth(LayoutMetrics.NUMERIC_INPUT_WIDTH)
        field.setClearButtonEnabled(False)
        field.setPlaceholderText(placeholder)
        return field

    def _create_separator(self, object_name: str) -> QFrame:
        line = QFrame(self)
        line.setObjectName(object_name)
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet(f"color: {Colors.BORDER_DEFAULT};")
        line.setFixedWidth(LayoutMetrics.SEPARATOR_THIN)
        return line

    def _apply_translations(self) -> None:
        """Apply current language strings to interactive controls."""
        if self._wavelength_header_label is not None:
            self._wavelength_header_label.setText(self.tr("Wavelength (Å)"))
        if self._flux_header_label is not None:
            self._flux_header_label.setText(self.tr("Flux"))
        if self._reset_button is not None:
            self._reset_button.setText(self.tr("Reset View"))
        if self._auto_adjust_button is not None:
            self._auto_adjust_button.setText(self.tr("Auto Adjust"))
        if self._display_menu_button is not None:
            self._display_menu_button.setText(self.tr("Display"))
        for label in self._min_labels:
            label.setText(self.tr("Min"))
        for label in self._max_labels:
            label.setText(self.tr("Max"))

    # --- Signal handlers ---------------------------------------------
    def _apply_wavelength_min(self, value: float) -> None:
        if self._values is None:
            self._reject_wavelength_min()
            return
        if not math.isfinite(value) or value >= self._values.wavelength_max:
            self._reject_wavelength_min()
            return
        self._values.wavelength_min = value
        self.wavelength_range_applied.emit(
            self._values.wavelength_min, self._values.wavelength_max
        )

    def _apply_wavelength_max(self, value: float) -> None:
        if self._values is None:
            self._reject_wavelength_max()
            return
        if not math.isfinite(value) or value <= self._values.wavelength_min:
            self._reject_wavelength_max()
            return
        self._values.wavelength_max = value
        self.wavelength_range_applied.emit(
            self._values.wavelength_min, self._values.wavelength_max
        )

    def _apply_flux_min(self, value: float) -> None:
        if self._values is None:
            self._reject_flux_min()
            return
        if not math.isfinite(value) or value >= self._values.flux_max:
            self._reject_flux_min()
            return
        self._values.flux_min = value
        self.flux_range_applied.emit(self._values.flux_min, self._values.flux_max)

    def _apply_flux_max(self, value: float) -> None:
        if self._values is None:
            self._reject_flux_max()
            return
        if not math.isfinite(value) or value <= self._values.flux_min:
            self._reject_flux_max()
            return
        self._values.flux_max = value
        self.flux_range_applied.emit(self._values.flux_min, self._values.flux_max)

    def _reject_wavelength_min(self) -> None:
        """Reject wavelength minimum edits and restore the last accepted value."""
        if self._values is not None:
            self._wavelength_min_ctrl.set_value(self._values.wavelength_min)
        self._show_invalid_feedback()

    def _reject_wavelength_max(self) -> None:
        """Reject wavelength maximum edits and restore the last accepted value."""
        if self._values is not None:
            self._wavelength_max_ctrl.set_value(self._values.wavelength_max)
        self._show_invalid_feedback()

    def _reject_flux_min(self) -> None:
        """Reject flux minimum edits and restore the last accepted value."""
        if self._values is not None:
            self._flux_min_ctrl.set_value(self._values.flux_min)
        self._show_invalid_feedback()

    def _reject_flux_max(self) -> None:
        """Reject flux maximum edits and restore the last accepted value."""
        if self._values is not None:
            self._flux_max_ctrl.set_value(self._values.flux_max)
        self._show_invalid_feedback()

    def _show_invalid_feedback(self) -> None:
        """Temporal red highlight for invalid ranges."""
        original = self.styleSheet()
        self.setStyleSheet(original + " background-color: #FFF0F0;")
        timer = QTimer(self)
        timer.setSingleShot(True)

        def restore_style() -> None:
            self.setStyleSheet(original)
            timer.deleteLater()

        timer.timeout.connect(restore_style)
        timer.start(350)
