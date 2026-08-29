"""Tests for the file type selection dialog Qt translations."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QDialogButtonBox
from pytestqt.qtbot import QtBot

from chappy.gui.dialogs.file_type_selection_dialog import FileTypeSelectionDialog
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate


class _FakeProjectIO:
    """Project I/O test double that serves FITS inspection metadata."""

    def __init__(self) -> None:
        self.info_paths: list[str] = []

    def get_fits_info(self, path: str) -> dict[str, object]:
        """Return deterministic FITS metadata for the dialog."""
        self.info_paths.append(path)
        return {"primary_shape": [77], "n_extensions": 2}


def _show_dialog(dialog: FileTypeSelectionDialog, qtbot: QtBot) -> None:
    """Show the dialog and wait until Qt marks it visible.

    Args:
        dialog: Dialog under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible, timeout=1000)


def _write_file_type_selection_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for FileTypeSelectionDialog.

    Args:
        ts_path: Output TS file path.
    """
    ts = ET.Element("TS", version="2.1", language="ja_JP")
    context = ET.SubElement(ts, "context")
    name = ET.SubElement(context, "name")
    name.text = "FileTypeSelectionDialog"
    translations = {
        "Select File Types": "ファイル種別を選択",
        "Flux": "フラックス",
        "Error": "誤差",
        "Ignore": "無視",
        "OK": "OK",
        "Cancel": "キャンセル",
    }
    for source_text, translation_text in translations.items():
        message = ET.SubElement(context, "message")
        source = ET.SubElement(message, "source")
        source.text = source_text
        translation = ET.SubElement(message, "translation")
        translation.text = translation_text
    ET.ElementTree(ts).write(ts_path, encoding="utf-8", xml_declaration=True)


def _compile_file_type_selection_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for FileTypeSelectionDialog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Returns:
        Directory containing ``chappy_ja.qm``.
    """
    if shutil.which("pyside6-lrelease") is None:
        pytest.skip("pyside6-lrelease is not available")

    catalog_root = tmp_path / "qt_catalogs"
    catalog_root.mkdir()
    ts_path = catalog_root / "chappy_ja.ts"
    qm_path = catalog_root / "chappy_ja.qm"
    _write_file_type_selection_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled dialog test catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_file_type_selection_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


def test_buttons_use_english_sources(qtbot: QtBot) -> None:
    """Verify common buttons use Qt source text without an installed translator."""
    dialog = FileTypeSelectionDialog(["flux.fits"], project_io=_FakeProjectIO())
    _show_dialog(dialog, qtbot)

    assert dialog.button_box is not None
    ok_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)
    cancel_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Cancel)

    assert ok_button is not None
    assert cancel_button is not None
    assert ok_button.text() == "OK"
    assert cancel_button.text() == "Cancel"


def test_fixed_labels_use_english_sources(qtbot: QtBot) -> None:
    """Verify dialog-specific labels use Qt source text without a translator."""
    dialog = FileTypeSelectionDialog(["flux.fits"], project_io=_FakeProjectIO())
    _show_dialog(dialog, qtbot)

    assert dialog.windowTitle() == "Select File Types"
    assert dialog.file_widgets["flux.fits"]["flux"].text() == "Flux"
    assert dialog.file_widgets["flux.fits"]["error"].text() == "Error"
    assert dialog.file_widgets["flux.fits"]["ignore"].text() == "Ignore"


def test_file_info_uses_project_io_inspection(qtbot: QtBot) -> None:
    """Verify FITS info displayed in the dialog comes from ProjectIOUseCase."""
    fake_project_io = _FakeProjectIO()
    dialog = FileTypeSelectionDialog(["flux.fits"], project_io=fake_project_io)
    _show_dialog(dialog, qtbot)

    assert fake_project_io.info_paths == ["flux.fits"]
    assert dialog._info_labels["flux.fits"].text() == "77 pixels • 2 extensions"


def test_qt_translator_updates_existing_buttons(
    qtbot: QtBot, qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Verify common buttons update from Qt LanguageChange events."""
    dialog = FileTypeSelectionDialog(["flux.fits"], project_io=_FakeProjectIO())
    _show_dialog(dialog, qtbot)

    assert dialog.button_box is not None
    cancel_button = dialog.button_box.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel_button is not None

    state = qt_translator_installer.install_language("ja")

    assert state.app_translator_loaded
    dialog.changeEvent(QEvent(QEvent.Type.LanguageChange))
    qtbot.waitUntil(lambda: cancel_button.text() == "キャンセル", timeout=1000)

    qt_translator_installer.install_language("en")
    dialog.changeEvent(QEvent(QEvent.Type.LanguageChange))
    qtbot.waitUntil(lambda: cancel_button.text() == "Cancel", timeout=1000)


def test_lupdate_extracts_file_type_selection_common_buttons(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated dialog sources without old keys."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/dialogs/file_type_selection_dialog.py")],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    expected_sources = {
        "Select File Types",
        "Flux",
        "Error",
        "Ignore",
        "{count} pixels",
        "Shape: {shape}",
        "{count} extensions",
        "Error: {message}",
        "FITS file",
        "No Flux File Selected",
        "Please select at least one file as 'Flux'.",
        "Multiple Flux Files",
        "OK",
        "Cancel",
    }
    assert expected_sources.issubset(sources)
    assert not any("DLG__" in source for source in sources)
    assert not any("GUI__" in source for source in sources)
