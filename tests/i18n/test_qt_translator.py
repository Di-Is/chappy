"""Tests for the Qt translator migration installer."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chappy.i18n.qt_translator import QtCatalogLookup, QtTranslatorInstaller


class _LanguageChangeProbe(QWidget):
    """Widget that records LanguageChange events."""

    def __init__(self) -> None:
        """Create the probe widget."""
        super().__init__()
        self.language_change_count = 0

    def changeEvent(self, event: QEvent) -> None:
        """Record LanguageChange events.

        Args:
            event: Qt change event.
        """
        if event.type() == QEvent.Type.LanguageChange:
            self.language_change_count += 1
        super().changeEvent(event)


def _write_phase2_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog.

    Args:
        ts_path: Output TS file path.
    """
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                "<!DOCTYPE TS>",
                '<TS version="2.1" language="ja_JP">',
                "<context>",
                "<name>Phase2Probe</name>",
                "<message>",
                "<source>Hello</source>",
                "<translation>こんにちは</translation>",
                "</message>",
                "</context>",
                "</TS>",
            ]
        ),
        encoding="utf-8",
    )


def _write_catalog_lookup_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for direct lookup tests.

    Args:
        ts_path: Output TS file path.
    """
    ts_path.parent.mkdir(parents=True, exist_ok=True)
    ts_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                "<!DOCTYPE TS>",
                '<TS version="2.1" language="ja_JP">',
                "<context>",
                "<name>LookupProbe</name>",
                "<message>",
                "<source>Preview</source>",
                "<translation>プレビュー</translation>",
                "</message>",
                "</context>",
                "</TS>",
            ]
        ),
        encoding="utf-8",
    )


def _release_catalog(ts_path: Path, qm_path: Path) -> None:
    """Compile a TS catalog to QM with pyside6-lrelease.

    Args:
        ts_path: Input TS file path.
        qm_path: Output QM file path.
    """
    qm_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pyside6-lrelease", str(ts_path), "-qm", str(qm_path)],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(shutil.which("pyside6-lrelease") is None, reason="pyside6-lrelease not found")
def test_install_language_loads_app_catalog_and_emits_language_change(
    tmp_path: Path, qtbot: QtBot
) -> None:
    """Verify application catalog loading, retention, and removal.

    Args:
        tmp_path: Temporary directory provided by pytest.
        qtbot: Qt bot fixture.
    """
    translation_root = tmp_path / "app_i18n"
    qt_translation_root = tmp_path / "qt_i18n"
    qt_translation_root.mkdir()
    ts_path = translation_root / "chappy_ja.ts"
    qm_path = translation_root / "chappy_ja.qm"
    _write_phase2_ts(ts_path)
    _release_catalog(ts_path, qm_path)
    probe = _LanguageChangeProbe()
    qtbot.addWidget(probe)
    probe.show()
    installer = QtTranslatorInstaller(
        translation_root=translation_root, qt_translation_root=qt_translation_root
    )

    try:
        state = installer.install_language("ja")
        QCoreApplication.processEvents()

        assert state.language_code == "ja"
        assert state.app_catalog_path == qm_path
        assert state.app_translator_loaded is True
        assert state.qtbase_catalog_path == qt_translation_root / "qtbase_ja.qm"
        assert state.qtbase_translator_loaded is False
        assert installer.app_translator_loaded is True
        assert QCoreApplication.translate("Phase2Probe", "Hello") == "こんにちは"
        assert probe.language_change_count >= 1

        fallback_state = installer.install_language("en")
        QCoreApplication.processEvents()

        assert fallback_state.language_code == "en"
        assert fallback_state.app_translator_loaded is False
        assert installer.app_translator_loaded is False
        assert QCoreApplication.translate("Phase2Probe", "Hello") == "Hello"
    finally:
        installer.remove_translators()


def test_missing_app_and_qtbase_catalogs_do_not_fail(tmp_path: Path) -> None:
    """Verify missing catalogs are reported without raising.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    translation_root = tmp_path / "missing_app_i18n"
    qt_translation_root = tmp_path / "missing_qt_i18n"
    installer = QtTranslatorInstaller(
        translation_root=translation_root, qt_translation_root=qt_translation_root
    )

    state = installer.install_language("ja_JP")

    assert state.language_code == "ja"
    assert state.app_catalog_path == translation_root / "chappy_ja.qm"
    assert state.app_translator_loaded is False
    assert state.qtbase_catalog_path == qt_translation_root / "qtbase_ja.qm"
    assert state.qtbase_translator_loaded is False
    assert installer.app_translator_loaded is False
    assert installer.qtbase_translator_loaded is False


@pytest.mark.skipif(shutil.which("pyside6-lrelease") is None, reason="pyside6-lrelease not found")
def test_qt_catalog_lookup_translates_without_installing_catalog(tmp_path: Path) -> None:
    """Verify direct catalog lookup does not install a global translator.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    translation_root = tmp_path / "app_i18n"
    ts_path = translation_root / "chappy_ja.ts"
    qm_path = translation_root / "chappy_ja.qm"
    _write_catalog_lookup_ts(ts_path)
    _release_catalog(ts_path, qm_path)
    lookup = QtCatalogLookup(translation_root=translation_root)

    assert lookup.translate("ja", "LookupProbe", "Preview") == "プレビュー"
    assert lookup.translate("en", "LookupProbe", "Preview") == "Preview"
    assert lookup.translate("ja", "LookupProbe", "Missing") == "Missing"
    assert QCoreApplication.translate("LookupProbe", "Preview") == "Preview"


def test_qt_catalog_lookup_missing_catalog_falls_back_to_source(tmp_path: Path) -> None:
    """Verify direct catalog lookup falls back when no QM catalog exists.

    Args:
        tmp_path: Temporary directory provided by pytest.
    """
    lookup = QtCatalogLookup(translation_root=tmp_path / "missing_i18n")

    assert lookup.translate("ja_JP", "LookupProbe", "Preview") == "Preview"


@pytest.mark.skipif(shutil.which("pyside6-lrelease") is None, reason="pyside6-lrelease not found")
def test_qtbase_catalog_load_is_optional_but_retained_when_available(
    tmp_path: Path, qtbot: QtBot
) -> None:
    """Verify optional Qt base catalogs can be loaded and retained.

    Args:
        tmp_path: Temporary directory provided by pytest.
        qtbot: Qt bot fixture.
    """
    _ = qtbot
    translation_root = tmp_path / "missing_app_i18n"
    qt_translation_root = tmp_path / "qt_i18n"
    qt_translation_root.mkdir()
    ts_path = qt_translation_root / "qtbase_ja.ts"
    qm_path = qt_translation_root / "qtbase_ja.qm"
    _write_phase2_ts(ts_path)
    _release_catalog(ts_path, qm_path)
    installer = QtTranslatorInstaller(
        translation_root=translation_root, qt_translation_root=qt_translation_root
    )

    try:
        state = installer.install_language("ja")

        assert state.app_translator_loaded is False
        assert state.qtbase_catalog_path == qm_path
        assert state.qtbase_translator_loaded is True
        assert installer.qtbase_translator_loaded is True
        assert QCoreApplication.translate("Phase2Probe", "Hello") == "こんにちは"
    finally:
        installer.remove_translators()
