"""Tests for the spectral resolution dialog."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Generator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QLabel, QPushButton
from pytestqt.qtbot import QtBot

from chappy.core.resolution import (
    RESOLUTION_CONSTRAINTS,
    SETTINGS_RESOLUTION_ENABLED_KEY,
    SETTINGS_RESOLUTION_VALUE_KEY,
)
from chappy.gui.dialogs.resolution_dialog import ResolutionDialog
from scripts.i18n_lupdate import run_lupdate


RESOLUTION_DIALOG_QT_SOURCES = {
    "Resolution Settings",
    "Configure the spectral resolution R = λ/Δλ for the current spectrum.",
    "Spectral Resolution R:",
    "(dimensionless)",
    "Range: {min} - {max:,}",
    "Apply instrumental resolution",
    "Spectral Resolution R = λ/Δλ",
    "Resolution value input",
    "Resolution range hint",
    "Include instrumental resolution effects in the model",
    "Cancel",
    "OK",
    "Please enter a valid number",
    "Please enter a value of {min} or greater",
    "Please enter a value of {max:,} or less",
}


@pytest.fixture
def isolated_settings(tmp_path: Path) -> Generator[QSettings, None, None]:
    """Provide isolated settings storage for each test."""

    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(settings_dir))
    settings = QSettings("TestOrg", "ResolutionDialogTests")
    settings.clear()
    yield settings
    settings.clear()


def _ts_sources(ts_path: Path) -> set[str]:
    """Return source texts extracted into a Qt TS file."""

    tree = ET.parse(ts_path)
    return {source.text for source in tree.findall(".//source") if source.text is not None}


def _spin(dialog: ResolutionDialog) -> QDoubleSpinBox:
    spin = dialog.findChild(QDoubleSpinBox, "resolutionSpin")
    assert spin is not None, "Resolution spinbox missing"
    return spin


def _error_label(dialog: ResolutionDialog) -> QLabel:
    label = dialog.findChild(QLabel, "resolutionErrorLabel")
    assert label is not None
    return label


def _apply_checkbox(dialog: ResolutionDialog) -> QCheckBox:
    checkbox = dialog.findChild(QCheckBox, "applyResolutionCheckbox")
    assert checkbox is not None
    return checkbox


def _button(dialog: ResolutionDialog, name: str) -> QPushButton:
    button = dialog.findChild(QPushButton, name)
    assert button is not None, f"Missing button {name}"
    return button


def test_dialog_loads_stored_settings(qtbot: QtBot, isolated_settings: QSettings) -> None:
    isolated_settings.setValue(SETTINGS_RESOLUTION_VALUE_KEY, 42000.0)
    isolated_settings.setValue(SETTINGS_RESOLUTION_ENABLED_KEY, False)

    dialog = ResolutionDialog(None, settings=isolated_settings)
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.waitExposed(dialog)

    assert _spin(dialog).value() == pytest.approx(42000.0)
    assert _apply_checkbox(dialog).isChecked() is False


def test_invalid_value_disables_ok(qtbot: QtBot, isolated_settings: QSettings) -> None:
    dialog = ResolutionDialog(None, settings=isolated_settings)
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.waitExposed(dialog)

    spin = _spin(dialog)
    line_edit = spin.lineEdit()
    assert line_edit is not None
    line_edit.setText("5")

    ok_button = _button(dialog, "okButton")
    qtbot.waitUntil(lambda: not ok_button.isEnabled())

    err = _error_label(dialog)
    assert err.isVisible()
    assert str(int(RESOLUTION_CONSTRAINTS["min"])) in err.text()


def test_ok_persists_settings(qtbot: QtBot, isolated_settings: QSettings) -> None:
    dialog = ResolutionDialog(None, settings=isolated_settings)
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.waitExposed(dialog)

    spin = _spin(dialog)
    spin.setValue(51500.0)
    checkbox = _apply_checkbox(dialog)
    checkbox.setChecked(False)

    with qtbot.waitSignal(dialog.resolution_applied, timeout=500) as signal:
        QTest.mouseClick(_button(dialog, "okButton"), Qt.MouseButton.LeftButton)

    value, enabled = signal.args
    assert value == pytest.approx(51500.0)
    assert enabled is False

    stored_value = isolated_settings.value(SETTINGS_RESOLUTION_VALUE_KEY, type=float)
    stored_enabled = isolated_settings.value(SETTINGS_RESOLUTION_ENABLED_KEY, type=bool)
    assert stored_value == pytest.approx(51500.0)
    assert stored_enabled is False


def test_resolution_value_raises_when_spinbox_missing(
    qtbot: QtBot, isolated_settings: QSettings
) -> None:
    dialog = ResolutionDialog(None, settings=isolated_settings)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._spinbox = None

    with pytest.raises(RuntimeError, match="Resolution spinbox was not initialized"):
        _ = dialog.resolution_value


def test_validate_resolution_field_raises_without_error_label(
    qtbot: QtBot, isolated_settings: QSettings
) -> None:
    dialog = ResolutionDialog(None, settings=isolated_settings)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._error_label = None

    with pytest.raises(RuntimeError, match="Resolution error label was not initialized"):
        dialog._validate_resolution_field()


def test_resolution_dialog_uses_qt_source_text(qtbot: QtBot, isolated_settings: QSettings) -> None:
    """Verify migrated GUI strings use Qt source text."""

    dialog = ResolutionDialog(None, settings=isolated_settings)
    qtbot.addWidget(dialog)
    dialog.show()

    qtbot.waitExposed(dialog)

    spin = _spin(dialog)
    assert spin.toolTip() == "Spectral Resolution R = λ/Δλ"
    assert spin.accessibleName() == "Resolution value input"
    assert _apply_checkbox(dialog).toolTip() == (
        "Include instrumental resolution effects in the model"
    )
    assert _button(dialog, "cancelButton").text() == "Cancel"
    assert _button(dialog, "okButton").text() == "OK"

    line_edit = spin.lineEdit()
    assert line_edit is not None
    line_edit.setText("")
    qtbot.waitUntil(lambda: _error_label(dialog).isVisible())
    assert _error_label(dialog).text() == "Please enter a valid number"


def test_lupdate_extracts_resolution_dialog_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated ResolutionDialog GUI sources."""

    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "resolution_dialog.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/dialogs/resolution_dialog.py")], ts_output=ts_path
    )

    sources = _ts_sources(ts_path)
    assert RESOLUTION_DIALOG_QT_SOURCES <= sources
    assert not any("GUI__" in source or "DLG__" in source for source in sources)


def test_format_number_raises_type_error_if_qt_api_returns_non_string(
    qtbot: QtBot, isolated_settings: QSettings
) -> None:
    """Fail fast when QLocale.toString returns an invalid type."""

    class NonStringLocale:
        def toString(self, *_args: object, **_kwargs: object) -> object:
            return 3.14

    dialog = ResolutionDialog(None, settings=isolated_settings)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog._locale = NonStringLocale()

    with pytest.raises(TypeError, match="Expected QLocale.toString\\(\\) to return str"):
        dialog._format_number(12345.0)
