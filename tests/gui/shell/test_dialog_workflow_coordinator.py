"""Tests for shell dialog workflow wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QWidget

from chappy.gui.dialogs.cosmology_dialog import CosmologyDialog
from chappy.gui.shell.dialog_workflow_coordinator import (
    DialogWorkflowCoordinator,
    DialogWorkflowPorts,
)
from chappy.core.spectroscopy_project import SpectroscopyProject

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from pytestqt.qtbot import QtBot


class _ShellSignals(QObject):
    """Signal source standing in for the main window."""

    language_changed = Signal(str)
    project_changed = Signal(object)


class _CosmologyNotifier:
    """Test notifier that records cosmology change calls."""

    def __init__(self) -> None:
        self.call_count = 0

    def notify_cosmology_changed(self) -> None:
        self.call_count += 1


def _make_coordinator(
    parent: QWidget,
    signals: _ShellSignals,
    notifier: _CosmologyNotifier,
    *,
    project: SpectroscopyProject | None = None,
    resolution_updates: MagicMock | None = None,
    resolution_history_recorder: MagicMock | None = None,
) -> DialogWorkflowCoordinator:
    """Build a coordinator whose non-cosmology dependencies are inert doubles."""
    updates = resolution_updates or MagicMock()
    history_recorder = resolution_history_recorder or MagicMock()
    return DialogWorkflowCoordinator(
        DialogWorkflowPorts(
            parent=parent,
            language_switcher=MagicMock(),
            language_changed_signal=signals.language_changed,
            project_changed_signal=signals.project_changed,
            user_manual_controller=MagicMock(),
            resolution_dialogs=MagicMock(),
            resolution_updates=updates,
            current_project_provider=lambda: project,
            project_file_path_provider=lambda: None,
            resolution_change_notifier_provider=lambda: None,
            resolution_history_recorder_provider=lambda: history_recorder,
            cosmology_change_notifier_provider=lambda: notifier,
            action_factory_provider=lambda: None,
            mode_shell_coordinator_provider=lambda: None,
            status_message=lambda _message, _timeout: None,
            preset_store=MagicMock(),
            atomic_data=MagicMock(),
        )
    )


def test_cosmology_dialog_apply_notifies_consumer(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Confirming the cosmology dialog should reach the injected notifier."""
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings")
    )

    parent = QWidget()
    qtbot.addWidget(parent)
    notifier = _CosmologyNotifier()
    coordinator = _make_coordinator(parent, _ShellSignals(), notifier)

    def _exec_and_apply(dialog: CosmologyDialog) -> int:
        dialog.parameters_applied.emit()
        return 1

    monkeypatch.setattr(CosmologyDialog, "exec", _exec_and_apply)

    coordinator.show_cosmology_dialog()

    assert notifier.call_count == 1


def test_resolution_confirmation_injects_shared_history_recorder(qtbot: QtBot) -> None:
    """The dialog slot must route user resolution edits through shared history."""
    parent = QWidget()
    qtbot.addWidget(parent)
    project = SpectroscopyProject()
    updates = MagicMock()
    history_recorder = MagicMock()
    coordinator = _make_coordinator(
        parent,
        _ShellSignals(),
        _CosmologyNotifier(),
        project=project,
        resolution_updates=updates,
        resolution_history_recorder=history_recorder,
    )

    coordinator._on_resolution_applied(48_000.0, True)

    updates.apply_resolution.assert_called_once_with(
        project, value=48_000.0, enabled=True, notifier=None, history_recorder=history_recorder
    )
