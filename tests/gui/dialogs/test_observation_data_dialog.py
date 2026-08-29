"""Tests for observation data selection dialog."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QDialog, QLineEdit, QPushButton
from pytestqt.qtbot import QtBot

from chappy.gui.dialogs.observation_data_dialog import ObservationDataDialog
from scripts.i18n_lupdate import run_lupdate


@pytest.fixture()
def dialog(qtbot: QtBot) -> ObservationDataDialog:
    """Create dialog instance added to qtbot."""
    dlg = ObservationDataDialog()
    qtbot.addWidget(dlg)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    qtbot.waitExposed(dlg)
    return dlg


def _get_widgets(dlg: ObservationDataDialog) -> tuple[QLineEdit, QLineEdit, QPushButton, QLabel]:
    flux_edit = dlg.findChild(QLineEdit, "fluxPathEdit")
    error_edit = dlg.findChild(QLineEdit, "errorPathEdit")
    ok_button = dlg.findChild(QPushButton, "okButton")
    message_label = dlg.findChild(QLabel, "validationLabel")

    assert flux_edit is not None
    assert error_edit is not None
    assert ok_button is not None
    assert message_label is not None

    return flux_edit, error_edit, ok_button, message_label


def test_focus_starts_on_flux_field(dialog: ObservationDataDialog, qtbot: QtBot) -> None:
    flux_edit, *_ = _get_widgets(dialog)
    qtbot.waitUntil(lambda: dialog.focusWidget() is flux_edit, timeout=2000)


def test_fixed_labels_use_english_sources(dialog: ObservationDataDialog) -> None:
    """Verify dialog-specific labels use Qt source text without a translator."""
    flux_edit, error_edit, *_ = _get_widgets(dialog)
    flux_label = dialog.findChild(QLabel, "fluxLabel")
    error_label = dialog.findChild(QLabel, "errorLabel")

    assert flux_label is not None
    assert error_label is not None
    assert dialog.windowTitle() == "Open Observation Data"
    assert flux_label.text() == "Flux data:"
    assert error_label.text() == "Error data:"
    assert flux_edit.placeholderText() == "Select the flux FITS file"
    assert error_edit.placeholderText() == "Select the error FITS file"


def test_validation_and_messages(
    dialog: ObservationDataDialog, qtbot: QtBot, tmp_path: Path
) -> None:
    flux_edit, error_edit, ok_button, message_label = _get_widgets(dialog)

    flux_file = tmp_path / "flux.fits"
    flux_file.write_bytes(b"")

    error_file = tmp_path / "error.fit"
    error_file.write_bytes(b"")

    invalid_ext = tmp_path / "notes.txt"
    invalid_ext.write_text("not fits")

    missing_file = tmp_path / "missing.fit"

    assert not ok_button.isEnabled()

    flux_edit.setText(str(flux_file))
    qtbot.waitUntil(lambda: not ok_button.isEnabled())

    error_edit.setText(str(error_file))
    qtbot.waitUntil(lambda: ok_button.isEnabled())
    assert not bool(error_edit.property("error"))

    # Nonexistent file keeps OK disabled but no message yet
    error_edit.setText(str(missing_file))
    qtbot.waitUntil(lambda: not ok_button.isEnabled())
    assert bool(error_edit.property("error"))
    assert not message_label.isVisible()

    # Invalid extension shows validation message immediately
    error_edit.setText(str(invalid_ext))
    qtbot.waitUntil(lambda: not ok_button.isEnabled())
    qtbot.waitUntil(lambda: message_label.isVisible())
    assert "FITS" in message_label.text()

    # Restore valid state clears message and enables OK
    error_edit.setText(str(error_file))
    qtbot.waitUntil(lambda: ok_button.isEnabled())
    qtbot.waitUntil(lambda: not message_label.isVisible())


def test_accept_sets_selected_paths(
    dialog: ObservationDataDialog, qtbot: QtBot, tmp_path: Path
) -> None:
    flux_edit, error_edit, ok_button, message_label = _get_widgets(dialog)

    flux_file = tmp_path / "flux.fits"
    flux_file.write_bytes(b"")

    error_file = tmp_path / "error.fit"
    error_file.write_bytes(b"")

    flux_edit.setText(str(flux_file))
    error_edit.setText(str(error_file))
    qtbot.waitUntil(lambda: ok_button.isEnabled())
    assert not message_label.isVisible()

    with qtbot.waitSignal(dialog.finished, timeout=500) as finished:
        QTest.mouseClick(ok_button, Qt.MouseButton.LeftButton)

    result_code = finished.args[0]
    assert result_code == int(QDialog.DialogCode.Accepted)
    assert dialog.flux_path == str(flux_file)
    assert dialog.error_path == str(error_file)


def test_lupdate_extracts_observation_data_common_button_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated dialog sources without old keys."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "observation_data_dialog_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/dialogs/observation_data_dialog.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    expected_sources = {
        "Open Observation Data",
        "Select the FITS files that contain your observed spectrum.",
        "Flux data:",
        "Select the flux FITS file",
        "Browse...",
        "Error data:",
        "Select the error FITS file",
        "OK",
        "Cancel",
        "Select FITS file",
        "FITS files (*.fits *.fit);;All files (*.*)",
        "Please provide valid FITS files for both flux and error.",
        "Selected file must be a FITS file (*.fits or *.fit)",
        "Invalid Selection",
    }
    assert expected_sources.issubset(sources)
    assert not any("DLG__" in source for source in sources)
    assert not any("GUI__" in source for source in sources)
