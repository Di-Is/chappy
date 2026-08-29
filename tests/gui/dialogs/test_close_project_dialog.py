"""Tests for the close project confirmation dialog."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from chappy.gui.dialogs.close_project_dialog import CloseProjectDialog
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate


def _ensure_visible(dialog: CloseProjectDialog, qtbot: QtBot) -> None:
    """Show the dialog and wait until Qt marks it visible.

    Args:
        dialog: Dialog under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.isVisible, timeout=1000)


def _write_close_project_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for CloseProjectDialog.

    Args:
        ts_path: Output TS file path.
    """
    ts_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ja_JP">
<context>
    <name>CloseProjectDialog</name>
    <message>
        <source>&amp;Close Project</source>
        <translation>プロジェクトを閉じる(&amp;C)</translation>
    </message>
    <message>
        <source>The current project has unsaved changes.
Do you want to save them?</source>
        <translation>現在のプロジェクトには未保存の変更があります。
保存しますか？</translation>
    </message>
    <message>
        <source>Name</source>
        <translation>名前</translation>
    </message>
    <message>
        <source>Closing returns to Start mode. Use File → Open Project to load it again.</source>
        <translation>閉じると開始モードに戻ります。「ファイル」→「プロジェクトを開く」で再度読み込めます。</translation>
    </message>
    <message>
        <source>Cancel</source>
        <translation>キャンセル</translation>
    </message>
    <message>
        <source>Don't Save</source>
        <translation>保存しない</translation>
    </message>
    <message>
        <source>Save</source>
        <translation>保存</translation>
    </message>
</context>
</TS>
""",
        encoding="utf-8",
    )


def _compile_close_project_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for CloseProjectDialog.

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
    _write_close_project_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled test Japanese catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_close_project_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


def test_english_source_fallback_without_project_name(qtbot: QtBot) -> None:
    """Show English source text when no Qt app translator is installed."""
    dialog = CloseProjectDialog()
    _ensure_visible(dialog, qtbot)

    assert dialog.windowTitle() == "&Close Project"

    message = dialog.findChild(QLabel, "closeProjectMessage")
    assert message is not None
    assert message.text() == "The current project has unsaved changes.\nDo you want to save them?"

    assert dialog._detail_label is None

    guidance = dialog.findChild(QLabel, "closeProjectGuidance")
    assert guidance is not None
    assert (
        guidance.text()
        == "Closing returns to Start mode. Use File → Open Project to load it again."
    )
    assert guidance.isVisible()

    assert dialog._cancel_button.text() == "Cancel"
    assert dialog._dont_save_button.text() == "Don't Save"
    assert dialog._save_button.text() == "Save"


def test_japanese_translator_updates_existing_dialog(
    qtbot: QtBot, qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Retranslate visible widgets after Qt installs a Japanese catalog."""
    project_name = "Alpha Centauri"
    dialog = CloseProjectDialog(project_name=project_name)
    _ensure_visible(dialog, qtbot)

    assert dialog.windowTitle() == "&Close Project"
    assert dialog._save_button.isDefault()

    state = qt_translator_installer.install_language("ja")
    assert state.app_translator_loaded
    qtbot.waitUntil(lambda: dialog.windowTitle() == "プロジェクトを閉じる(&C)", timeout=1000)

    message = dialog.findChild(QLabel, "closeProjectMessage")
    assert message is not None
    assert message.text() == "現在のプロジェクトには未保存の変更があります。\n保存しますか？"

    detail = dialog.findChild(QLabel, "closeProjectDetail")
    assert detail is not None
    assert detail.text() == f"名前: {project_name}"
    assert detail.isVisible()

    guidance = dialog.findChild(QLabel, "closeProjectGuidance")
    assert guidance is not None
    assert guidance.text() == (
        "閉じると開始モードに戻ります。「ファイル」→「プロジェクトを開く」で再度読み込めます。"
    )
    assert guidance.isVisible()

    assert dialog._cancel_button.text() == "キャンセル"
    assert dialog._dont_save_button.text() == "保存しない"
    assert dialog._save_button.text() == "保存"
    assert dialog._save_button.isDefault()

    qt_translator_installer.install_language("en")
    qtbot.waitUntil(lambda: dialog.windowTitle() == "&Close Project", timeout=1000)
    assert detail.text() == f"Name: {project_name}"
    assert detail.isVisible()


def test_lupdate_extracts_close_project_sources(tmp_path: Path) -> None:
    """Verify lupdate can extract the migrated CloseProjectDialog sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/dialogs/close_project_dialog.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert "&Close Project" in sources
    assert "The current project has unsaved changes.\nDo you want to save them?" in sources
    assert "Name" in sources
    assert "Closing returns to Start mode. Use File → Open Project to load it again." in sources
    assert "Cancel" in sources
    assert "Don't Save" in sources
    assert "Save" in sources
