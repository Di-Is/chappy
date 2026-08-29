"""Dialog and desktop-service adapters for the main window shell."""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from chappy.gui.dialogs.resolution_dialog import ResolutionDialog

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from PySide6.QtWidgets import QWidget

    from chappy.i18n import LanguageSwitcher


class ManualOpenResult(Enum):
    """Result of a user manual open request."""

    OPENED = auto()
    MISSING = auto()
    FAILED = auto()


class UserManualDialogAdapter:
    """Open user manual files and show related message boxes."""

    def open_manual(
        self,
        parent: QWidget,
        *,
        manual_path: Path | None,
        title: str,
        missing_message: str,
        failure_message: str,
    ) -> ManualOpenResult:
        """Open a manual file or report why it could not be opened.

        Args:
            parent: Parent widget for message boxes.
            manual_path: Manual entry file path.
            title: Dialog title.
            missing_message: Message shown when the manual is missing.
            failure_message: Message shown when desktop opening fails.

        Returns:
            Result describing the performed action.
        """
        if manual_path is None:
            QMessageBox.information(parent, title, missing_message)
            return ManualOpenResult.MISSING

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(manual_path))):
            QMessageBox.warning(parent, title, failure_message)
            return ManualOpenResult.FAILED

        return ManualOpenResult.OPENED


class ResolutionDialogAdapter:
    """Own the resolution dialog instance and its QSettings storage."""

    def __init__(self) -> None:
        """Initialize the adapter with shared resolution settings."""
        self._dialog: ResolutionDialog | None = None
        self._settings = QSettings()

    @property
    def has_active_dialog(self) -> bool:
        """Return whether a resolution dialog is currently active."""
        return self._dialog is not None

    def activate_existing(self) -> bool:
        """Raise the existing dialog when one is already active.

        Returns:
            True when an existing dialog was activated.
        """
        if self._dialog is None:
            return False
        self._dialog.raise_()
        self._dialog.activateWindow()
        return True

    def present(
        self,
        parent: QWidget,
        *,
        status_callback: Callable[[str, str], None],
        language_switcher: LanguageSwitcher,
        resolution_applied_slot: Callable[[float, bool], None],
        finished_slot: Callable[[int], None],
    ) -> None:
        """Create and execute a resolution dialog.

        Args:
            parent: Parent widget.
            status_callback: Dialog status callback.
            language_switcher: Runtime language switcher.
            resolution_applied_slot: Slot for applied resolution values.
            finished_slot: Slot for dialog finished events.
        """
        if self._dialog is not None:
            return

        dialog = ResolutionDialog(
            parent,
            settings=self._settings,
            status_callback=status_callback,
            language_switcher=language_switcher,
        )
        dialog.resolution_applied.connect(resolution_applied_slot)
        dialog.finished.connect(finished_slot)
        self._dialog = dialog
        dialog.exec()

    def clear_active(self) -> None:
        """Clear the active dialog reference."""
        self._dialog = None
