"""GUI adapter for optimize export dialogs and directory settings."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

EXPORT_LAST_DIRECTORY_KEY = "optimize/export/last_directory"


class OptimizeExportDialogAdapter:
    """Handle optimize export file dialogs and message boxes."""

    def __init__(self, parent: QWidget) -> None:
        """Initialize the adapter.

        Args:
            parent: Parent widget for modal dialogs.
        """
        self._parent = parent

    def prompt_export_path(
        self, default_filename: str, project_filename: str | None
    ) -> tuple[Path, str] | None:
        """Prompt user for export path and encoding.

        Args:
            default_filename: Suggested CSV filename.
            project_filename: Current project filename, if any.

        Returns:
            Tuple of output path and encoding, or None when cancelled.
        """
        directory = self.default_export_directory(project_filename)
        initial_csv = str(directory / default_filename)
        title = self._parent.tr("Export optimization results")
        filters = self._csv_filters()

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self._parent, title, initial_csv, filters
        )
        if not file_path:
            return None

        encoding = self._selected_encoding(selected_filter)
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        resolved_path = Path(file_path)
        self.cache_export_directory(resolved_path.parent)
        return resolved_path, encoding

    def default_export_directory(self, project_filename: str | None) -> Path:
        """Return preferred export directory.

        Args:
            project_filename: Current project filename, if any.

        Returns:
            Preferred directory.
        """
        settings = QSettings("Chappy", "Chappy")
        cached_path = settings.value(EXPORT_LAST_DIRECTORY_KEY)
        if isinstance(cached_path, str):
            directory = Path(cached_path).expanduser()
            if directory.exists() and directory.is_dir():
                return directory

        if project_filename:
            return Path(project_filename).resolve().parent
        return Path.home()

    def cache_export_directory(self, directory: Path) -> None:
        """Persist directory path for the next export operation.

        Args:
            directory: Directory to persist.
        """
        if not directory.exists() or not directory.is_dir():
            return

        settings = QSettings("Chappy", "Chappy")
        settings.setValue(EXPORT_LAST_DIRECTORY_KEY, str(directory))

    def show_export_error(self, error: Exception) -> None:
        """Show an export error message.

        Args:
            error: Exception raised during export.
        """
        title = self._parent.tr("Error")
        template = self._parent.tr("Failed to export results: {error}")
        QMessageBox.critical(self._parent, title, template.format(error=str(error)))

    def _csv_filters(self) -> str:
        """Build file dialog filters.

        Returns:
            Dialog filter string.
        """
        if sys.platform == "win32":
            filter_utf8 = self._parent.tr("CSV UTF-8 (*.csv)")
            filter_bom = self._parent.tr("CSV UTF-8 BOM - Excel (*.csv)")
            return f"{filter_bom};;{filter_utf8}"
        return self._parent.tr("CSV Files (*.csv)")

    def _selected_encoding(self, selected_filter: str) -> str:
        """Resolve export encoding from the selected dialog filter.

        Args:
            selected_filter: Filter selected by the user.

        Returns:
            Encoding name.
        """
        if sys.platform != "win32":
            return "utf-8"
        filter_bom = self._parent.tr("CSV UTF-8 BOM - Excel (*.csv)")
        return "utf-8-sig" if filter_bom in selected_filter else "utf-8"
