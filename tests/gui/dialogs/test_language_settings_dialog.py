"""Tests for the language settings dialog."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QComboBox, QPushButton
from pytestqt.qtbot import QtBot

from chappy.i18n import language_switcher as lm
from chappy.i18n.qt_translator import QtCatalogLookup
from chappy.i18n.language_switcher import LanguageSwitcher
from chappy.gui.dialogs.language_settings_dialog import LanguageSettingsDialog
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate

LANGUAGE_SETTINGS_SOURCES = {
    "Language Settings",
    "Select the display language.",
    "Preview",
    "Example interface text",
    "The language selection could not be saved.",
    "OK",
    "Cancel",
    "&File",
    "Open",
    "Open Project",
    "Open observation data / project",
    "Example: It will look like this",
}


@pytest.fixture(autouse=True)
def reset_language_singleton() -> Iterator[None]:
    """Reset the language switcher singleton around each test.

    Yields:
        Nothing.
    """
    lm._INSTANCE = None
    yield
    lm._INSTANCE = None


@pytest.fixture()
def language_switcher(tmp_path: Path) -> LanguageSwitcher:
    config_dir = tmp_path / "langcfg"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text('[ui]\nlanguage = "ja"\n', encoding="utf-8")
    switcher = LanguageSwitcher(config_dir=config_dir)
    return switcher


def _write_language_settings_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for LanguageSettingsDialog.

    Args:
        ts_path: Output TS file path.
    """
    ts = ET.Element("TS", version="2.1", language="ja_JP")
    context = ET.SubElement(ts, "context")
    name = ET.SubElement(context, "name")
    name.text = "LanguageSettingsDialog"
    translations = {
        "Language Settings": "言語設定",
        "Select the display language.": "表示言語を選択してください。",
        "Preview": "プレビュー",
        "Example interface text": "代表的なUIテキストの例",
        "Language resources could not be loaded. The previous language remains active.": (
            "言語リソースを読み込めませんでした。前の言語のままです。"
        ),
        "The language selection could not be saved.": "言語設定を保存できませんでした。",
        "Failed to load language resources": "言語リソースを読み込めませんでした",
        "OK": "OK",
        "Cancel": "キャンセル",
        "&File": "ファイル(&F)",
        "Open": "開く",
        "Open Project": "プロジェクトを開く",
        "Open observation data / project": "観測データを開く／プロジェクトを開く",
        "Example: It will look like this": "例：このように表示されます",
    }
    for source_text, translation_text in translations.items():
        message = ET.SubElement(context, "message")
        source = ET.SubElement(message, "source")
        source.text = source_text
        translation = ET.SubElement(message, "translation")
        translation.text = translation_text
    tree = ET.ElementTree(ts)
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)


@pytest.fixture()
def qt_catalog_lookup(tmp_path: Path) -> Iterator[QtCatalogLookup]:
    """Provide a direct Qt catalog lookup for language preview tests.

    Args:
        tmp_path: Temporary directory provided by pytest.

    Yields:
        Catalog lookup configured with a test Japanese catalog.
    """
    if shutil.which("pyside6-lrelease") is None:
        pytest.skip("pyside6-lrelease is not available")

    catalog_root = tmp_path / "qt_catalogs"
    catalog_root.mkdir()
    ts_path = catalog_root / "chappy_ja.ts"
    qm_path = catalog_root / "chappy_ja.qm"
    _write_language_settings_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    yield QtCatalogLookup(translation_root=catalog_root)


def _get_language_combo(dialog: LanguageSettingsDialog) -> QComboBox:
    """Return the language selection combo box.

    Args:
        dialog: Dialog under test.

    Returns:
        Language selection combo box.
    """
    combo = dialog.findChild(QComboBox, "languageComboBox")
    assert combo is not None, "Missing language combo box"
    return combo


def _get_button(dialog: LanguageSettingsDialog, name: str) -> QPushButton:
    button = dialog.findChild(QPushButton, name)
    assert button is not None, f"Missing button {name}"
    return button


def test_initial_selection_matches_switcher(
    qtbot: QtBot, language_switcher: LanguageSwitcher, qt_catalog_lookup: QtCatalogLookup
) -> None:
    language_switcher.set_language("en")

    dialog = LanguageSettingsDialog(
        language_switcher=language_switcher, qt_catalog_lookup=qt_catalog_lookup
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    combo = _get_language_combo(dialog)
    assert combo.currentData() == "en"
    assert combo.currentText() == "English"
    assert dialog.windowTitle() == "Language Settings"


def test_preview_updates_when_selecting_language(
    qtbot: QtBot, language_switcher: LanguageSwitcher, qt_catalog_lookup: QtCatalogLookup
) -> None:
    dialog = LanguageSettingsDialog(
        language_switcher=language_switcher, qt_catalog_lookup=qt_catalog_lookup
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    combo = _get_language_combo(dialog)
    combo.setCurrentIndex(combo.findData("ja"))

    preview_button = _get_button(dialog, "previewSampleButton")
    assert preview_button.text() == "プロジェクトを開く"
    assert preview_button.toolTip() == "観測データを開く／プロジェクトを開く"


def test_accept_changes_language_and_emits_signal(
    qtbot: QtBot, language_switcher: LanguageSwitcher, qt_catalog_lookup: QtCatalogLookup
) -> None:
    dialog = LanguageSettingsDialog(
        language_switcher=language_switcher, qt_catalog_lookup=qt_catalog_lookup
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)

    combo = _get_language_combo(dialog)
    combo.setCurrentIndex(combo.findData("en"))
    assert combo.currentData() == "en"

    switcher_spy = QSignalSpy(language_switcher.language_changed)

    ok_button = _get_button(dialog, "okButton")
    with qtbot.waitSignal(dialog.language_applied, timeout=1000) as applied:
        QTest.mouseClick(ok_button, Qt.MouseButton.LeftButton)

    assert applied.args == ["en"]
    assert switcher_spy.count() == 1
    assert switcher_spy.at(0)[0] == "en"
    assert language_switcher.current_language == "en"
    assert not dialog.isVisible()


def test_lupdate_extracts_language_settings_dialog_preview_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated LanguageSettingsDialog preview sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/dialogs/language_settings_dialog.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert sources == LANGUAGE_SETTINGS_SOURCES
    assert not any("GUI__" in source or "DLG__" in source for source in sources)
