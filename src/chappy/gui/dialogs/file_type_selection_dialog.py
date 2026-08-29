"""File type selection dialog for FITS files."""

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chappy.application.project_io_usecase import ProjectIOUseCase
from chappy.gui.dialog_sizing import enforce_translated_minimum_size
from chappy.gui.theme import Fonts, apply_button_variant
from chappy.gui.visual_tokens import DialogMetrics
from chappy.i18n import get_language_switcher

logger = logging.getLogger(__name__)


class FileTypeSelectionDialog(QDialog):
    """Dialog for selecting file types when multiple FITS files are dropped."""

    files_selected = Signal(dict)

    def __init__(
        self, fits_files: list[str], parent: QWidget | None = None, *, project_io: ProjectIOUseCase
    ) -> None:
        """Create the dialog for classifying the provided FITS files.

        Args:
            fits_files: FITS file paths to classify.
            parent: Optional parent widget.
            project_io: Project I/O use case used for FITS inspection.
        """
        super().__init__(parent)

        self.fits_files = fits_files
        self.file_widgets: dict[str, dict[str, QRadioButton]] = {}
        self.button_groups: dict[str, QButtonGroup] = {}
        self._info_labels: dict[str, QLabel] = {}
        self._file_info_cache: dict[str, dict[str, object]] = {}
        self._language_switcher = get_language_switcher(self)
        self._project_io = project_io

        self._instructions_label: QLabel | None = None
        self.button_box: QDialogButtonBox | None = None

        self._setup_ui()
        self._load_file_info()
        self._apply_translations()

        self._language_switcher.language_changed.connect(self._on_language_changed)

        logger.debug("File type selection dialog initialized with %d files", len(fits_files))

    def _setup_ui(self) -> None:
        self.setModal(True)

        layout = QVBoxLayout(self)

        self._instructions_label = QLabel(self)
        self._instructions_label.setWordWrap(True)
        layout.addWidget(self._instructions_label)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        scroll_widget = QWidget(scroll_area)
        scroll_area.setWidget(scroll_widget)

        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(12)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if isinstance(ok_btn, QPushButton):
            apply_button_variant(ok_btn, "primary")
        cancel_btn = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if isinstance(cancel_btn, QPushButton):
            apply_button_variant(cancel_btn, "secondary")
        layout.addWidget(self.button_box)

        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

    def _apply_translations(self) -> None:
        title = self.tr("Select File Types")
        self.setWindowTitle(title)
        self.setAccessibleName(title)

        if self._instructions_label is not None:
            instructions = self.tr(
                "Please specify the type of each FITS file:\n"
                "• Flux: Main spectrum data\n"
                "• Error: Error/uncertainty data\n"
                "• Ignore: Skip this file"
            )
            self._instructions_label.setText(instructions)
            self._instructions_label.setAccessibleDescription(instructions)

        # Update radio buttons and info labels for each file
        radio_texts = {
            "flux": self.tr("Flux"),
            "error": self.tr("Error"),
            "ignore": self.tr("Ignore"),
        }
        for file_path, widgets in self.file_widgets.items():
            for role, radio in widgets.items():
                if role in radio_texts:
                    radio.setText(radio_texts[role])
                    radio.setAccessibleName(radio_texts[role])
            info_label = self._info_labels.get(file_path)
            if info_label is not None:
                info_label.setText(self._format_file_info(file_path))

        if self.button_box is not None:
            ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
            cancel_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
            ok_text = self.tr("OK")
            cancel_text = self.tr("Cancel")
            if ok_button is not None:
                ok_button.setText(ok_text)
                ok_button.setAccessibleName(ok_text)
            if cancel_button is not None:
                cancel_button.setText(cancel_text)
                cancel_button.setAccessibleName(cancel_text)

        enforce_translated_minimum_size(
            self,
            floor=QSize(*DialogMetrics.MIN_SIZE_FILE_TYPE_SELECTION),
            initial=QSize(*DialogMetrics.MIN_SIZE_FILE_TYPE_SELECTION),
        )

    def _on_language_changed(self, _code: str) -> None:
        self._apply_translations()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Retranslate Qt-managed labels when the application translator changes.

        Args:
            event: Qt change event delivered to this dialog.
        """
        super().changeEvent(event)
        if event.type() == QEvent.Type.LanguageChange:
            self._apply_translations()

    def _load_file_info(self) -> None:
        for file_path in self.fits_files:
            self._create_file_widget(file_path)

    def _create_file_widget(self, file_path: str) -> None:
        group = QGroupBox(Path(file_path).name, self)
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(8)

        info_label = QLabel(self)
        info_label.setStyleSheet(f"color: gray; font-size: {Fonts.SIZE_TINY};")
        group_layout.addWidget(info_label)
        self._info_labels[file_path] = info_label

        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(12)

        button_group = QButtonGroup(self)
        self.button_groups[file_path] = button_group

        flux_radio = QRadioButton(self)
        error_radio = QRadioButton(self)
        ignore_radio = QRadioButton(self)

        button_group.addButton(flux_radio, 0)
        button_group.addButton(error_radio, 1)
        button_group.addButton(ignore_radio, 2)

        radio_layout.addWidget(flux_radio)
        radio_layout.addWidget(error_radio)
        radio_layout.addWidget(ignore_radio)
        radio_layout.addStretch()

        group_layout.addLayout(radio_layout)
        self.scroll_layout.addWidget(group)

        self.file_widgets[file_path] = {
            "flux": flux_radio,
            "error": error_radio,
            "ignore": ignore_radio,
        }

        try:
            fits_info = self._project_io.get_fits_info(file_path)
            self._file_info_cache[file_path] = {"info": fits_info}
        except (OSError, ValueError, TypeError) as exc:
            self._file_info_cache[file_path] = {"error": str(exc)}

        info_label.setText(self._format_file_info(file_path))

        guessed = self._guess_file_type(file_path)
        if guessed == "flux":
            flux_radio.setChecked(True)
        elif guessed == "error":
            error_radio.setChecked(True)
        elif file_path == self.fits_files[0]:
            flux_radio.setChecked(True)
        else:
            ignore_radio.setChecked(True)

    def _format_file_info(self, file_path: str) -> str:
        record = self._file_info_cache.get(file_path)
        if not record:
            return self.tr("FITS file")

        if "error" in record:
            template = self.tr("Error: {message}")
            return template.format(message=record["error"])

        raw_fits_info = record.get("info", {})
        if not isinstance(raw_fits_info, dict):
            return self.tr("FITS file")
        fits_info: dict[str, object] = raw_fits_info
        info_parts: list[str] = []

        shape = fits_info.get("primary_shape")
        if isinstance(shape, (list, tuple)) and len(shape) > 0:
            if len(shape) == 1:
                template = self.tr("{count} pixels")
                info_parts.append(template.format(count=shape[0]))
            else:
                template = self.tr("Shape: {shape}")
                info_parts.append(template.format(shape=shape))

        n_ext = fits_info.get("n_extensions")
        if isinstance(n_ext, int) and n_ext > 1:
            template = self.tr("{count} extensions")
            info_parts.append(template.format(count=n_ext))

        if "error" in fits_info:
            template = self.tr("Error: {message}")
            info_parts.append(template.format(message=fits_info["error"]))

        if not info_parts:
            return self.tr("FITS file")
        return " • ".join(info_parts)

    def _guess_file_type(self, file_path: str) -> str:
        file_name = Path(file_path).name.lower()

        error_indicators = ["err", "error", "sigma", "unc", "uncertainty", "noise"]
        for indicator in error_indicators:
            if indicator in file_name:
                return "error"

        stem = Path(file_path).stem.lower()
        if stem.endswith("e"):
            return "error"
        if stem.endswith("f"):
            return "flux"

        return "flux"

    def _on_accept(self) -> None:
        flux_file = None
        error_files: list[str] = []
        ignored_files: list[str] = []
        flux_count = 0

        for file_path, widgets in self.file_widgets.items():
            if widgets["flux"].isChecked():
                if flux_file is None:
                    flux_file = file_path
                else:
                    ignored_files.append(file_path)
                flux_count += 1
            elif widgets["error"].isChecked():
                error_files.append(file_path)
            else:
                ignored_files.append(file_path)

        if flux_file is None:
            QMessageBox.warning(
                self,
                self.tr("No Flux File Selected"),
                self.tr("Please select at least one file as 'Flux'."),
            )
            return

        if flux_count > 1 and flux_file is not None:
            message_template = self.tr(
                "Multiple files were marked as 'Flux'. "
                "Only the first one will be used as the main spectrum.\n"
                "Using: {filename}"
            )
            QMessageBox.information(
                self,
                self.tr("Multiple Flux Files"),
                message_template.format(filename=Path(flux_file).name),
            )

        result = {
            "flux_file": flux_file,
            "error_files": error_files,
            "ignored_files": ignored_files,
        }

        self.files_selected.emit(result)
        self.accept()

        logger.info(
            "File type selection completed: flux=%s, errors=%d, ignored=%d",
            Path(flux_file).name if flux_file else "None",
            len(error_files),
            len(ignored_files),
        )


__all__ = ["FileTypeSelectionDialog"]
