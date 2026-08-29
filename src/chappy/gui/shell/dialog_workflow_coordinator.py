"""Own shell dialog workflows and their follow-up wiring."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from chappy.gui.dialogs.cosmology_dialog import CosmologyDialog
from chappy.gui.dialogs.language_settings_dialog import LanguageSettingsDialog
from chappy.gui.modes.identify.presets.preset_list_dialog import PresetListDialog
from chappy.gui.shell.dependencies import DialogCommandPort
from chappy.infrastructure.atomic_lines import USER_CSV_FILENAME, user_csv_directory

if TYPE_CHECKING:
    from collections.abc import Callable

    from PySide6.QtCore import SignalInstance
    from PySide6.QtWidgets import QWidget

    from chappy.application.history import ResolutionHistoryRecorder
    from chappy.application.optimize import CosmologyChangeNotifier
    from chappy.core.atomic_data import AtomicLineData
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
    from chappy.gui.shell.dialog_coordinator import ResolutionDialogAdapter
    from chappy.gui.shell.menu_action_factory import MenuActionFactory
    from chappy.gui.shell.mode_shell_coordinator import ModeShellCoordinator
    from chappy.gui.shell.resolution_update_adapter import (
        ResolutionChangeNotifier,
        ResolutionUpdateAdapter,
    )
    from chappy.gui.shell.user_manual_controller import UserManualController
    from chappy.i18n import LanguageSwitcher


@dataclass(frozen=True, slots=True)
class DialogWorkflowPorts:
    """Dependencies required by shell dialog workflows."""

    parent: QWidget
    language_switcher: LanguageSwitcher
    language_changed_signal: SignalInstance
    project_changed_signal: SignalInstance
    user_manual_controller: UserManualController
    resolution_dialogs: ResolutionDialogAdapter
    resolution_updates: ResolutionUpdateAdapter
    current_project_provider: Callable[[], SpectroscopyProject | None]
    project_file_path_provider: Callable[[], str | None]
    resolution_change_notifier_provider: Callable[[], ResolutionChangeNotifier | None]
    resolution_history_recorder_provider: Callable[[], ResolutionHistoryRecorder]
    cosmology_change_notifier_provider: Callable[[], CosmologyChangeNotifier | None]
    action_factory_provider: Callable[[], MenuActionFactory | None]
    mode_shell_coordinator_provider: Callable[[], ModeShellCoordinator | None]
    status_message: Callable[[str, int], None]
    preset_store: IdentifyPresetStore
    atomic_data: AtomicLineData


class DialogWorkflowCoordinator(DialogCommandPort):
    """Own global dialog commands and resolution prompting."""

    def __init__(self, ports: DialogWorkflowPorts) -> None:
        """Store dialog workflow dependencies."""
        self._ports = ports
        self._resolution_project_ref: SpectroscopyProject | None = None
        self._ports.language_changed_signal.connect(self.handle_language_changed)
        self._ports.project_changed_signal.connect(self.handle_project_changed)

    def open_user_manual(self) -> None:
        """Open the locally generated user manual in the default viewer."""
        self._ports.user_manual_controller.open_manual(
            self._ports.parent,
            title=QCoreApplication.translate("MainWindow", "&User Guide"),
            missing_message=QCoreApplication.translate(
                "MainWindow", "Contextual help is under development."
            ),
            failure_message=QCoreApplication.translate(
                "MainWindow",
                "Could not open the user guide. Please verify that the manual has been generated.",
            ),
        )

    def show_cosmology_dialog(self) -> None:
        """Show the cosmology parameter dialog."""
        dialog = CosmologyDialog(
            self._ports.parent, status_callback=self._handle_dialog_status_with_level
        )
        dialog.parameters_applied.connect(self._on_cosmology_applied)
        dialog.exec()

    def show_resolution_dialog(self) -> None:
        """Show spectral resolution configuration dialog."""
        if self._ports.resolution_dialogs.activate_existing():
            return

        self._resolution_project_ref = self._ports.current_project_provider()
        self._present_resolution_dialog()

    def open_line_database_folder(self) -> None:
        """Open the folder where a replacement spectral line CSV can be placed."""
        directory = user_csv_directory()
        try:
            directory.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        except OSError:
            opened = False

        if not opened:
            #: Keep {path} unchanged; it is replaced with the folder location.
            failure_template = QCoreApplication.translate(
                "MainWindow", "Could not open the folder. It is located at {path}."
            )
            QMessageBox.warning(
                self._ports.parent,
                QCoreApplication.translate("MainWindow", "Line Database Folder"),
                failure_template.format(path=directory),
            )
            return

        #: Keep {filename} unchanged; it is replaced with the CSV file name.
        hint_template = QCoreApplication.translate(
            "MainWindow", "Place {filename} in this folder and restart Chappy to use it."
        )
        self._handle_dialog_status(hint_template.format(filename=USER_CSV_FILENAME), 8000)

    def show_language_dialog(self) -> None:
        """Show language selection dialog."""
        dialog = LanguageSettingsDialog(
            self._ports.parent, language_switcher=self._ports.language_switcher
        )
        dialog.language_applied.connect(self._handle_language_applied)
        dialog.exec()

    def show_preset_list_dialog(self) -> None:
        """Show dialog for managing absorption presets."""
        dialog = PresetListDialog(
            self._ports.parent, self._ports.preset_store, atomic_data=self._ports.atomic_data
        )
        dialog.exec()

    def handle_project_changed(self, project: SpectroscopyProject | None) -> None:
        """Prompt for spectral resolution when a new project is activated."""
        if project is None:
            self._resolution_project_ref = None
            return

        if os.environ.get("CHAPPY_DOC_HEADLESS"):
            self._resolution_project_ref = project
            return

        previous_project = self._resolution_project_ref
        self._resolution_project_ref = project

        if self._ports.resolution_dialogs.has_active_dialog:
            return

        if project is previous_project:
            return

        if project.resolution_state.enabled:
            return

        if self._project_should_skip_resolution_prompt():
            return

        def _show_dialog() -> None:
            if self._resolution_project_ref is not project:
                return
            self._present_resolution_dialog()

        QTimer.singleShot(0, _show_dialog)

    def handle_language_changed(self, _language_code: str) -> None:
        """Refresh action and mode UI text when the runtime language changes."""
        action_factory = self._ports.action_factory_provider()
        if action_factory is not None:
            action_factory.retranslate(self._ports.language_switcher)

        mode_shell = self._ports.mode_shell_coordinator_provider()
        if mode_shell is not None and mode_shell.mode_state_store is not None:
            mode_shell.retranslate_context_bar()

    def _present_resolution_dialog(self) -> None:
        """Present the spectral resolution configuration dialog."""
        if self._ports.resolution_dialogs.has_active_dialog:
            return

        self._ports.resolution_dialogs.present(
            self._ports.parent,
            status_callback=self._handle_dialog_level_status,
            language_switcher=self._ports.language_switcher,
            resolution_applied_slot=self._on_resolution_applied,
            finished_slot=self._on_resolution_dialog_closed,
        )

    def _project_should_skip_resolution_prompt(self) -> bool:
        """Return whether resolution prompting should be skipped."""
        filename = self._ports.project_file_path_provider()
        if not filename:
            return False
        return Path(filename).suffix.lower() in {".h5", ".hdf5"}

    def _on_resolution_applied(self, value: float, enabled: bool) -> None:
        """Handle resolution dialog confirmation."""
        message_template = QCoreApplication.translate("MainWindow", "Applied resolution R={R}")
        value_text = f"{value:,.0f}" if value >= 1000 else f"{value:g}"
        self._emit_status(message_template.format(R=value_text), 4000)

        project = self._ports.current_project_provider()
        if project is not None:
            self._ports.resolution_updates.apply_resolution(
                project,
                value=value,
                enabled=enabled,
                notifier=self._ports.resolution_change_notifier_provider(),
                history_recorder=self._ports.resolution_history_recorder_provider(),
            )

    def _on_cosmology_applied(self) -> None:
        """Propagate confirmed cosmology changes to interested consumers."""
        notifier = self._ports.cosmology_change_notifier_provider()
        if notifier is not None:
            notifier.notify_cosmology_changed()

    def _on_resolution_dialog_closed(self, _result: int) -> None:
        """Cleanup references when the resolution dialog closes."""
        self._ports.resolution_dialogs.clear_active()

    def _handle_language_applied(self, language_code: str) -> None:
        """Show feedback after applying a new language."""
        label = self._ports.language_switcher.label_for(language_code)
        template = QCoreApplication.translate("MainWindow", "Language switched to {label}")
        self._emit_status(template.format(label=label), 3000)

    def _emit_status(self, message: str, timeout_ms: int) -> None:
        """Emit a shell status message."""
        self._ports.status_message(message, timeout_ms)

    def _handle_dialog_status(self, message: str, timeout_ms: int) -> None:
        """Bridge dialog status callbacks to the status bar."""
        duration = timeout_ms if timeout_ms > 0 else 3000
        self._emit_status(message, duration)

    def _handle_dialog_status_with_level(self, message: str, timeout_ms: int, level: str) -> None:
        """Bridge dialog status callbacks carrying severity information."""
        duration = timeout_ms if timeout_ms > 0 else 3000
        if level.lower() == "error":
            duration = max(duration, 5000)
        self._emit_status(message, duration)

    def _handle_dialog_level_status(self, message: str, level: str) -> None:
        """Bridge dialog status callbacks that provide only severity."""
        duration = 5000 if level.lower() == "error" else 3000
        self._emit_status(message, duration)
