"""Dialog for selecting observed flux and error FITS files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.dialog_sizing import enforce_translated_minimum_size
from chappy.gui.theme import Colors, Fonts, apply_button_variant
from chappy.gui.visual_tokens import DialogMetrics
from chappy.i18n import get_language_switcher

if TYPE_CHECKING:
    from PySide6.QtGui import QShowEvent

FITS_EXTENSIONS = {".fits", ".fit"}


@dataclass(slots=True)
class _FieldValidationResult:
    """Result of validating an individual path entry."""

    is_valid: bool
    message: str | None = None


class ObservationDataDialog(QDialog):
    """Modal dialog requesting flux and error FITS files from the user."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Set up widgets, styles, and translation hooks."""
        super().__init__(parent)
        self.setObjectName("observationDataDialog")
        self.setModal(True)

        self._language_switcher = get_language_switcher(self)

        self._flux_path: str | None = None
        self._error_path: str | None = None

        self._header_label: QLabel | None = None
        self._flux_label: QLabel | None = None
        self._error_label: QLabel | None = None
        self._flux_path_edit: QLineEdit | None = None
        self._error_path_edit: QLineEdit | None = None
        self._validation_label: QLabel | None = None
        self._ok_button: QPushButton | None = None
        self._button_box: QDialogButtonBox | None = None
        self._flux_browse_button: QPushButton | None = None
        self._error_browse_button: QPushButton | None = None

        self._build_ui()
        self._connect_signals()
        self._apply_styles()
        self._apply_translations()
        self._validate_inputs(show_message=False)
        self._language_switcher.language_changed.connect(self._on_language_changed)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Focus the flux field when the dialog becomes visible."""
        super().showEvent(event)
        # Ensure the dialog is the active window so focus can be applied reliably
        # across platforms (notably under automated GUI tests).
        self.raise_()
        self.activateWindow()
        # Hint focus to the dialog (delegated to proxy), then reinforce
        # with a zero-timeout singleShot once the event loop settles.
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self._focus_flux_field()
        # Reinforce focus shortly after show to avoid races under load
        QTimer.singleShot(0, self._activate_and_focus_flux_field)
        QTimer.singleShot(100, self._focus_flux_field)
        QTimer.singleShot(200, self._focus_flux_field)

    def _activate_and_focus_flux_field(self) -> None:
        """Activate the window and focus the flux-path field.

        Qt does not always apply focus to a widget unless the window is the active
        window. This helper is invoked via `QTimer.singleShot` from `showEvent` to
        retry activation once the event loop is running.
        """
        self.activateWindow()
        self._focus_flux_field()

    def _focus_flux_field(self) -> None:
        """Set focus to the flux-path field and select contents.

        This is called via `QTimer.singleShot(0, ...)` from `showEvent`
        to avoid races where another child widget grabs focus after the
        dialog becomes visible. The method is idempotent and safe to call
        multiple times.
        """
        if self._flux_path_edit is None:
            return
        # Use OtherFocusReason to work in headless tests where the
        # window may not be the active window.
        self._flux_path_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self._flux_path_edit.selectAll()

    @property
    def flux_path(self) -> str | None:
        """Return the validated flux FITS path if dialog accepted."""
        return self._flux_path

    @property
    def error_path(self) -> str | None:
        """Return the validated error FITS path if dialog accepted."""
        return self._error_path

    def selected_paths(self) -> tuple[str | None, str | None]:
        """Return tuple of (flux_path, error_path)."""
        return self._flux_path, self._error_path

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        self._header_label = QLabel(self)
        self._header_label.setWordWrap(True)
        self._header_label.setObjectName("dialogHeader")
        layout.addWidget(self._header_label)

        form_container = QWidget(self)
        form_layout = QGridLayout(form_container)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(12)

        self._flux_label = QLabel(self)
        self._flux_label.setObjectName("fluxLabel")
        form_layout.addWidget(self._flux_label, 0, 0, Qt.AlignmentFlag.AlignVCenter)

        self._flux_path_edit = QLineEdit(self)
        self._flux_path_edit.setObjectName("fluxPathEdit")
        form_layout.addWidget(self._flux_path_edit, 0, 1)
        # Delegate dialog focus to the primary input field
        self.setFocusProxy(self._flux_path_edit)

        self._flux_browse_button = QPushButton(self)
        self._flux_browse_button.setObjectName("fluxBrowseButton")
        apply_button_variant(self._flux_browse_button, "secondary")
        form_layout.addWidget(self._flux_browse_button, 0, 2)

        self._error_label = QLabel(self)
        self._error_label.setObjectName("errorLabel")
        form_layout.addWidget(self._error_label, 1, 0, Qt.AlignmentFlag.AlignVCenter)

        self._error_path_edit = QLineEdit(self)
        self._error_path_edit.setObjectName("errorPathEdit")
        form_layout.addWidget(self._error_path_edit, 1, 1)

        self._error_browse_button = QPushButton(self)
        self._error_browse_button.setObjectName("errorBrowseButton")
        apply_button_variant(self._error_browse_button, "secondary")
        form_layout.addWidget(self._error_browse_button, 1, 2)

        layout.addWidget(form_container)

        divider = QFrame(self)
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider)

        self._validation_label = QLabel("", self)
        self._validation_label.setObjectName("validationLabel")
        self._validation_label.setVisible(False)
        layout.addWidget(self._validation_label)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok,
            Qt.Orientation.Horizontal,
            self,
        )
        self._button_box.setObjectName("dialogButtonBox")
        self._ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if self._ok_button:
            self._ok_button.setObjectName("okButton")
            self._ok_button.setEnabled(False)
            apply_button_variant(self._ok_button, "primary")

        cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if isinstance(cancel_button, QPushButton):
            cancel_button.setObjectName("cancelButton")
            apply_button_variant(cancel_button, "secondary")

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self._button_box)
        layout.addLayout(buttons_layout)

    def _apply_styles(self) -> None:
        if self._header_label:
            self._header_label.setStyleSheet(f"font-size: {Fonts.SIZE_LARGE};")

        for label in (self._flux_label, self._error_label):
            if label:
                label.setStyleSheet("font-weight: bold;")

        if self._validation_label:
            self._validation_label.setStyleSheet(
                f"color: {Colors.ERROR}; font-size: {Fonts.SIZE_NORMAL};"
            )

        if self._ok_button:
            self._ok_button.setMinimumWidth(90)

        if self._button_box:
            cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if cancel_button:
                cancel_button.setMinimumWidth(90)

    def _connect_signals(self) -> None:
        if not self._flux_path_edit or not self._error_path_edit:
            return

        self._flux_path_edit.textChanged.connect(self._on_path_changed)
        self._error_path_edit.textChanged.connect(self._on_path_changed)

        if self._flux_browse_button:
            self._flux_browse_button.clicked.connect(self._on_browse_flux)
        if self._error_browse_button:
            self._error_browse_button.clicked.connect(self._on_browse_error)

        if self._button_box is None:
            return

        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)

    def _apply_translations(self) -> None:
        title = self.tr("Open Observation Data")
        self.setWindowTitle(title)
        self.setAccessibleName(title)

        if self._header_label:
            header_text = self.tr("Select the FITS files that contain your observed spectrum.")
            self._header_label.setText(header_text)
            self._header_label.setAccessibleDescription(header_text)

        if self._flux_label:
            flux_label = self.tr("Flux data:")
            self._flux_label.setText(flux_label)
            self._flux_label.setAccessibleName(flux_label)

        if self._flux_path_edit:
            placeholder = self.tr("Select the flux FITS file")
            self._flux_path_edit.setPlaceholderText(placeholder)

        if self._flux_browse_button:
            browse_text = self.tr("Browse...")
            self._flux_browse_button.setText(browse_text)
            self._flux_browse_button.setAccessibleName(browse_text)

        if self._error_label:
            error_label = self.tr("Error data:")
            self._error_label.setText(error_label)
            self._error_label.setAccessibleName(error_label)

        if self._error_path_edit:
            placeholder = self.tr("Select the error FITS file")
            self._error_path_edit.setPlaceholderText(placeholder)

        if self._error_browse_button:
            browse_text = self.tr("Browse...")
            self._error_browse_button.setText(browse_text)
            self._error_browse_button.setAccessibleName(browse_text)

        if self._button_box:
            ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_button = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
            ok_text = self.tr("OK")
            cancel_text = self.tr("Cancel")
            if ok_button:
                ok_button.setText(ok_text)
                ok_button.setAccessibleName(ok_text)
            if cancel_button:
                cancel_button.setText(cancel_text)
                cancel_button.setAccessibleName(cancel_text)

        enforce_translated_minimum_size(
            self, floor=QSize(DialogMetrics.MIN_WIDTH_DEFAULT, DialogMetrics.MIN_HEIGHT_DEFAULT)
        )

    def _on_language_changed(self, _code: str) -> None:
        self._apply_translations()
        self._validate_inputs(show_message=False)

    def _on_browse_flux(self) -> None:
        self._browse_for_file(self._flux_path_edit)

    def _on_browse_error(self) -> None:
        self._browse_for_file(self._error_path_edit)

    def _browse_for_file(self, target: QLineEdit | None) -> None:
        if target is None:
            return

        # Determine starting directory with priority:
        # 1. Last used directory from QSettings
        # 2. Directory from text field if valid
        # 3. Home directory as fallback
        settings = QSettings()
        last_dir_raw = settings.value("recent_directories/fits", defaultValue="", type=str)

        start_dir: Path | None = None
        if isinstance(last_dir_raw, str) and last_dir_raw.strip():
            candidate_dir = Path(last_dir_raw).expanduser()
            if candidate_dir.exists():
                start_dir = candidate_dir

        if start_dir is None and target.text().strip():
            text_path = Path(target.text()).expanduser()
            if text_path.exists() and text_path.is_dir():
                start_dir = text_path
            elif text_path.exists() and text_path.is_file():
                start_dir = text_path.parent

        if start_dir is None or not start_dir.exists() or not start_dir.is_dir():
            start_dir = Path.home()

        dialog_title = self.tr("Select FITS file")
        filter_text = self.tr("FITS files (*.fits *.fit);;All files (*.*)")
        file_path, _ = QFileDialog.getOpenFileName(self, dialog_title, str(start_dir), filter_text)
        if file_path:
            target.setText(file_path)
            # Save the parent directory for next time
            selected_path = Path(file_path)
            settings.setValue("recent_directories/fits", str(selected_path.parent))

    def _on_path_changed(self, _new_value: str) -> None:
        self._validate_inputs(show_message=False)

    def _validate_inputs(self, show_message: bool) -> bool:
        if self._flux_path_edit is None or self._error_path_edit is None:
            return False

        flux_result = self._validate_path(self._flux_path_edit.text(), self._flux_path_edit)
        error_result = self._validate_path(self._error_path_edit.text(), self._error_path_edit)
        is_valid = flux_result.is_valid and error_result.is_valid

        message = flux_result.message or error_result.message
        if self._validation_label:
            if message:
                self._validation_label.setText(message)
                self._validation_label.setVisible(True)
            elif show_message and not is_valid:
                reminder = self.tr("Please provide valid FITS files for both flux and error.")
                self._validation_label.setText(reminder)
                self._validation_label.setVisible(True)
            else:
                self._validation_label.clear()
                self._validation_label.setVisible(False)

        if self._ok_button:
            self._ok_button.setEnabled(is_valid)

        return is_valid

    def _validate_path(self, value: str, field: QLineEdit) -> _FieldValidationResult:
        normalized = value.strip()
        if not normalized:
            self._set_field_error(field, True)
            return _FieldValidationResult(False)

        path = Path(normalized).expanduser()
        if not path.exists() or not path.is_file():
            self._set_field_error(field, True)
            return _FieldValidationResult(False)

        if path.suffix.lower() not in FITS_EXTENSIONS:
            self._set_field_error(field, True)
            return _FieldValidationResult(
                False, self.tr("Selected file must be a FITS file (*.fits or *.fit)")
            )

        self._set_field_error(field, False)
        return _FieldValidationResult(True)

    def _set_field_error(self, field: QLineEdit, error: bool) -> None:
        field.setProperty("error", error)
        field.style().unpolish(field)
        field.style().polish(field)
        field.update()

    def _on_accept(self) -> None:
        if not self._validate_inputs(show_message=True):
            if self._validation_label and not self._validation_label.isVisible():
                QMessageBox.warning(
                    self,
                    self.tr("Invalid Selection"),
                    self.tr("Please provide valid FITS files for both flux and error."),
                )
            return

        if self._flux_path_edit is None or self._error_path_edit is None:
            return

        flux_path = str(Path(self._flux_path_edit.text().strip()).expanduser())
        error_path = str(Path(self._error_path_edit.text().strip()).expanduser())

        self._flux_path = flux_path
        self._error_path = error_path
        self.accept()


__all__ = ["ObservationDataDialog"]
