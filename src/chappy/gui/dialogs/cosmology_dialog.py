"""Cosmology parameter dialog implementation (SCR-DIA-COS)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QLocale, QSettings, QSize, Qt, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from chappy.core.conversion import coerce_float
from chappy.core.cosmology import (
    COSMOLOGY_CONSTRAINTS,
    PLANCK_2018,
    CosmologyParameters,
    is_spatially_flat,
)
from chappy.gui.dialog_sizing import enforce_translated_minimum_size
from chappy.gui.theme import Fonts, apply_action_row_sizing, apply_button_variant
from chappy.gui.visual_tokens import DialogMetrics

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True)
class _FieldControl:
    """Hold widgets and metadata for a numeric entry field.

    Attributes:
        key: Stable field key.
        spinbox: Numeric input widget.
        error_label: Validation error label.
        label: Field label widget.
        unit_label: Unit label widget.
        minimum: Minimum allowed value.
        maximum: Maximum allowed value.
        decimals: Number of displayed decimal places.
        step: Spinbox increment.
    """

    key: str
    spinbox: QDoubleSpinBox
    error_label: QLabel
    label: QLabel
    unit_label: QLabel
    minimum: float
    maximum: float
    decimals: int
    step: float


class CosmologyDialog(QDialog):
    """Modal dialog to edit ΛCDM cosmology parameters."""

    parameters_applied = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
        status_callback: Callable[[str, int, str], None] | None = None,
        initial_parameters: CosmologyParameters | None = None,
    ) -> None:
        """Initialize the dialog and prime it with persisted parameters.

        Args:
            parent: Parent widget.
            settings: Settings object used for persistence.
            status_callback: Optional callback for user-facing status messages.
            initial_parameters: Initial parameters overriding persisted settings.
        """
        super().__init__(parent)

        self._settings = settings or QSettings()
        self._status_callback = status_callback
        self._fields: dict[str, _FieldControl] = {}
        self._current_parameters = initial_parameters or self._load_from_settings()
        self._description_label: QLabel | None = None
        self._omega_k_label: QLabel | None = None
        self._omega_k_info_icon: QLabel | None = None

        self._setup_ui()
        self._apply_parameters(self._current_parameters)
        self._update_omega_k_display()
        self._validate_all()
        self._retranslate_ui()

    def _setup_ui(self) -> None:
        """Create dialog widgets and wire signal handlers."""
        self.setModal(True)
        self.setProperty("role", "dialog")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(16)

        self._description_label = QLabel(self)
        self._description_label.setWordWrap(True)
        self._description_label.setObjectName("cosmologyDescription")
        main_layout.addWidget(self._description_label)

        form_container = QWidget(self)
        form_layout = QVBoxLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(12)

        h0_widget, self._fields["h0"] = self._create_field(
            parent=form_container, field_key="h0", constraints=COSMOLOGY_CONSTRAINTS["h0"]
        )
        form_layout.addWidget(h0_widget)
        form_layout.addWidget(self._fields["h0"].error_label)

        om_widget, self._fields["omega_m"] = self._create_field(
            parent=form_container,
            field_key="omega_m",
            constraints=COSMOLOGY_CONSTRAINTS["omega_m"],
        )
        form_layout.addWidget(om_widget)
        form_layout.addWidget(self._fields["omega_m"].error_label)

        ol_widget, self._fields["omega_lambda"] = self._create_field(
            parent=form_container,
            field_key="omega_lambda",
            constraints=COSMOLOGY_CONSTRAINTS["omega_lambda"],
        )
        form_layout.addWidget(ol_widget)
        form_layout.addWidget(self._fields["omega_lambda"].error_label)

        main_layout.addWidget(form_container)

        main_layout.addWidget(self._create_separator())

        main_layout.addWidget(self._create_omega_k_section())

        self._defaults_button = QPushButton(self)
        self._defaults_button.setObjectName("defaultsButton")
        self._defaults_button.clicked.connect(self._apply_defaults)
        apply_button_variant(self._defaults_button, "secondary")
        apply_action_row_sizing(self._defaults_button)
        main_layout.addWidget(self._defaults_button, alignment=Qt.AlignmentFlag.AlignLeft)

        main_layout.addWidget(self._create_separator())

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        button_row.addWidget(spacer)

        self._cancel_button = QPushButton(self)
        self._cancel_button.setObjectName("cancelButton")
        self._cancel_button.clicked.connect(self.reject)
        apply_button_variant(self._cancel_button, "secondary")
        button_row.addWidget(self._cancel_button)

        self._ok_button = QPushButton(self)
        self._ok_button.setObjectName("okButton")
        self._ok_button.setDefault(True)
        self._ok_button.clicked.connect(self._on_accept_clicked)
        apply_button_variant(self._ok_button, "primary")
        button_row.addWidget(self._ok_button)

        apply_action_row_sizing(self._cancel_button, self._ok_button)

        main_layout.addLayout(button_row)

        # Focus initial field after layout is ready
        self._fields["h0"].spinbox.setFocus(Qt.FocusReason.OtherFocusReason)

    def _create_field(
        self, *, parent: QWidget, field_key: str, constraints: dict[str, float]
    ) -> tuple[QWidget, _FieldControl]:
        """Create one numeric cosmology input row.

        Args:
            parent: Parent widget for the row.
            field_key: Stable key identifying the cosmology parameter.
            constraints: Numeric bounds and formatting options.

        Returns:
            Row widget and its field control metadata.
        """
        container = QWidget(parent)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        label = QLabel("", container)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.setMinimumWidth(170)
        label.setObjectName(f"label_{field_key}")
        row.addWidget(label)

        spinbox = QDoubleSpinBox(container)
        spinbox.setObjectName(f"spin_{field_key}")
        spinbox.setDecimals(int(constraints.get("decimals", 3)))
        spinbox.setRange(float(constraints.get("min", 0.0)), float(constraints.get("max", 1.0)))
        spinbox.setSingleStep(float(constraints.get("step", 0.001)))
        spinbox.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        spinbox.setAccelerated(True)
        spinbox.setMaximumWidth(140)
        spinbox.setKeyboardTracking(False)
        label.setBuddy(spinbox)
        row.addWidget(spinbox)

        unit_label = QLabel("", container)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        unit_label.setObjectName(f"unit_{field_key}")
        row.addWidget(unit_label)
        row.addStretch()

        error_label = QLabel("", parent)
        error_label.setVisible(False)
        error_label.setObjectName(f"error_{field_key}")
        error_label.setStyleSheet(f"color: #d93025; font-size: {Fonts.SIZE_NORMAL};")
        error_label.setProperty("aria-live", "assertive")

        field_control = _FieldControl(
            key=field_key,
            spinbox=spinbox,
            error_label=error_label,
            label=label,
            unit_label=unit_label,
            minimum=float(constraints.get("min", 0.0)),
            maximum=float(constraints.get("max", 1.0)),
            decimals=int(constraints.get("decimals", 3)),
            step=float(constraints.get("step", 0.001)),
        )

        # Connect signals after control is fully initialized
        spinbox.valueChanged.connect(self._handle_value_changed)
        if spinbox.lineEdit():
            spinbox.lineEdit().textChanged.connect(self._handle_text_changed)

        return container, field_control

    def _create_separator(self) -> QFrame:
        """Create a horizontal separator line.

        Returns:
            Separator frame.
        """
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #e0e0e0;")
        return line

    def _create_omega_k_section(self) -> QWidget:
        """Create the derived Ωk display row.

        Returns:
            Widget containing the derived Ωk controls.
        """
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        icon_label = QLabel(container)
        icon = QIcon.fromTheme("dialog-information")
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        icon_label.setPixmap(icon.pixmap(16, 16))
        self._omega_k_info_icon = icon_label
        layout.addWidget(icon_label)

        label = QLabel("", container)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._omega_k_label = label
        layout.addWidget(label)

        self._omega_k_value = QLabel("0.000", container)
        self._omega_k_value.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._omega_k_value.setObjectName("omegaKValue")
        self._omega_k_value.setProperty("aria-live", "polite")
        layout.addWidget(self._omega_k_value)

        self._flat_badge = QLabel("", container)
        self._flat_badge.setVisible(False)
        self._flat_badge.setStyleSheet(
            "color: #1b5e20; background-color: #c8e6c9;"
            f"border-radius: 6px; padding: 2px 8px; font-size: {Fonts.SIZE_SMALL};"
        )
        layout.addWidget(self._flat_badge)

        layout.addStretch()

        return container

    def _apply_field_translations(self, control: _FieldControl) -> None:
        """Apply translated label and unit text to one field.

        Args:
            control: Field control to update.
        """
        if control.key == "h0":
            control.label.setText(self.tr("Hubble Constant H₀"))
            control.unit_label.setText(self.tr("km/s/Mpc"))
        elif control.key == "omega_m":
            control.label.setText(self.tr("Matter Density Ωm"))
            control.unit_label.setText(self.tr("(dimensionless)"))
        elif control.key == "omega_lambda":
            control.label.setText(self.tr("Dark Energy Density ΩΛ"))
            control.unit_label.setText(self.tr("(dimensionless)"))
        else:
            msg = f"Unsupported cosmology field: {control.key}"
            raise ValueError(msg)

    def _retranslate_ui(self) -> None:
        """Apply current Qt translations to all visible dialog text."""
        title = self.tr("Cosmology Parameters")
        self.setWindowTitle(title)
        self.setAccessibleName(title)

        if self._description_label is not None:
            self._description_label.setText(
                self.tr(
                    "Set parameters for ΛCDM cosmology.\n"
                    "Ωk is derived as 1−Ωm−ΩΛ from H₀, Ωm, ΩΛ and used to compute "
                    "comoving distance and lookback time.\n"
                )
            )

        for control in self._fields.values():
            self._apply_field_translations(control)

        h0_control = self._fields.get("h0")
        if h0_control is not None and h0_control.spinbox.lineEdit() is not None:
            placeholder = self.tr("67.4")
            h0_control.spinbox.lineEdit().setPlaceholderText(placeholder)

        if self._omega_k_info_icon is not None:
            self._omega_k_info_icon.setToolTip(
                self.tr("Ωk is informational (non-flat ΛCDM allowed)")
            )

        if self._omega_k_label is not None:
            self._omega_k_label.setText(self.tr("Derived: Ωk"))

        self._flat_badge.setText(self.tr("flat"))

        self._defaults_button.setText(self.tr("Apply Planck2018"))
        self._cancel_button.setText(self.tr("Cancel"))
        self._ok_button.setText(self.tr("OK"))

        if self._flat_badge.isVisible():
            self._flat_badge.setAccessibleDescription(self.tr("Universe is within flat tolerance"))
        else:
            self._flat_badge.setAccessibleDescription("")

        self._validate_all()

        enforce_translated_minimum_size(
            self, floor=QSize(DialogMetrics.MIN_WIDTH_DEFAULT, DialogMetrics.MIN_HEIGHT_DEFAULT)
        )

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Retranslate the dialog when Qt sends a language change event.

        Args:
            event: Qt change event.
        """
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate_ui()
            self._update_omega_k_display()
        super().changeEvent(event)

    @property
    def omega_k(self) -> float:
        """Current derived Ωk."""
        return self._current_parameters.omega_k

    @property
    def parameters(self) -> CosmologyParameters:
        """Return the currently validated cosmology parameters."""
        return self._current_parameters

    @Slot(float)
    def _handle_value_changed(self, _value: float) -> None:
        """Refresh validation and derived values after spinbox changes."""
        self._validate_all()
        self._update_omega_k_display()

    @Slot(str)
    def _handle_text_changed(self, _text: str) -> None:
        """Refresh validation and derived values after raw text edits."""
        self._validate_all()
        self._update_omega_k_display()

    @Slot()
    def _apply_defaults(self) -> None:
        """Apply Planck 2018 defaults and notify listeners."""
        self._apply_parameters(PLANCK_2018)
        self._update_omega_k_display()
        self._validate_all()
        self._show_status_message(self.tr("Applied Planck2018 defaults"), level="success")

    @Slot()
    def _on_accept_clicked(self) -> None:
        """Persist valid values and accept the dialog."""
        if not self._update_current_parameters():
            return

        params = self._current_parameters
        self._write_to_settings(params)
        self._show_status_message(
            self.tr("Applied cosmology parameters (H₀={H0}, Ωm={Om}, ΩΛ={Ol}, Ωk={Ok})").format(
                H0=f"{params.h0:.1f}",
                Om=f"{params.omega_m:.3f}",
                Ol=f"{params.omega_lambda:.3f}",
                Ok=f"{params.omega_k:.3f}",
            ),
            level="success",
        )
        self.parameters_applied.emit()
        super().accept()

    def _validate_field(self, *, _key: str, control: _FieldControl) -> bool:
        """Validate a single field and update its error presentation.

        Args:
            _key: Field key kept for compatibility with existing call sites.
            control: Field control to validate.

        Returns:
            True when the current field value is valid.
        """
        line_edit = control.spinbox.lineEdit()
        text = line_edit.text() if line_edit else control.spinbox.text()
        text = text.strip()

        locale = control.spinbox.locale() if line_edit else QLocale()
        value, ok = locale.toDouble(text)

        message = ""
        is_valid = ok and control.minimum <= value <= control.maximum

        if not ok:
            message = self.tr("Please enter a valid number")
        elif value < control.minimum or value > control.maximum:
            message = self._validation_range_message(control.key)

        control.error_label.setVisible(not is_valid)
        control.error_label.setText(message)
        control.error_label.setAccessibleDescription(message)
        control.spinbox.setStyleSheet(
            "border: 1px solid #d93025; background-color: rgba(217,48,37,0.05);"
            if not is_valid
            else ""
        )
        control.spinbox.setAccessibleDescription(message if not is_valid else "")

        return is_valid

    def _validation_range_message(self, field_key: str) -> str:
        """Return the translated range error for a field.

        Args:
            field_key: Stable key identifying the cosmology parameter.

        Returns:
            Translated validation message.
        """
        if field_key == "h0":
            return self.tr("H₀ must be between 50.0 and 100.0 km/s/Mpc")
        if field_key == "omega_m":
            return self.tr("Ωm must be between 0.0 and 1.0")
        if field_key == "omega_lambda":
            return self.tr("ΩΛ must be between 0.0 and 1.0")
        msg = f"Unsupported cosmology field: {field_key}"
        raise ValueError(msg)

    def _validate_all(self) -> bool:
        """Validate all fields and update the OK button state.

        Returns:
            True when every field is valid.
        """
        all_valid = True
        for control in self._fields.values():
            if not self._validate_field(_key=control.key, control=control):
                all_valid = False
        self._ok_button.setEnabled(all_valid)
        return all_valid

    def _update_current_parameters(self) -> bool:
        """Update the current parameter snapshot from validated fields.

        Returns:
            True when field values were valid and parameters were updated.
        """
        if not self._validate_all():
            return False

        self._current_parameters = CosmologyParameters(
            h0=self._fields["h0"].spinbox.value(),
            omega_m=self._fields["omega_m"].spinbox.value(),
            omega_lambda=self._fields["omega_lambda"].spinbox.value(),
        )
        return True

    def _update_omega_k_display(self) -> None:
        """Refresh the derived Ωk value and flat badge state."""
        if not self._update_current_parameters():
            return

        value = self._current_parameters.omega_k
        self._omega_k_value.setText(f"{value:+0.3f}")
        is_flat = is_spatially_flat(value)
        self._flat_badge.setVisible(is_flat)
        if is_flat:
            self._flat_badge.setAccessibleDescription(self.tr("Universe is within flat tolerance"))
        else:
            self._flat_badge.setAccessibleDescription("")

    def _load_from_settings(self) -> CosmologyParameters:
        """Load persisted cosmology parameters from settings.

        Returns:
            Persisted parameters or Planck 2018 defaults.
        """

        def _read(key: str, default: float) -> float:
            raw: object = self._settings.value(key, default)
            return coerce_float(raw, default=default)

        return CosmologyParameters(
            h0=_read("settings/cosmology/H0", PLANCK_2018.h0),
            omega_m=_read("settings/cosmology/Om", PLANCK_2018.omega_m),
            omega_lambda=_read("settings/cosmology/Ol", PLANCK_2018.omega_lambda),
        )

    def _write_to_settings(self, params: CosmologyParameters) -> None:
        """Persist cosmology parameters to settings.

        Args:
            params: Parameters to persist.
        """
        self._settings.setValue("settings/cosmology/H0", params.h0)
        self._settings.setValue("settings/cosmology/Om", params.omega_m)
        self._settings.setValue("settings/cosmology/Ol", params.omega_lambda)
        self._settings.sync()

    def _apply_parameters(self, params: CosmologyParameters) -> None:
        """Apply parameters to the spinbox controls.

        Args:
            params: Parameters to display.
        """
        self._current_parameters = params
        self._fields["h0"].spinbox.setValue(params.h0)
        self._fields["omega_m"].spinbox.setValue(params.omega_m)
        self._fields["omega_lambda"].spinbox.setValue(params.omega_lambda)

    def _show_status_message(
        self, message: str, timeout_ms: int = 3000, *, level: str = "info"
    ) -> None:
        """Send a status message through the optional callback.

        Args:
            message: Message text.
            timeout_ms: Display duration in milliseconds.
            level: Visual status level.
        """
        if self._status_callback:
            self._status_callback(message, timeout_ms, level)


__all__ = ["CosmologyDialog"]
