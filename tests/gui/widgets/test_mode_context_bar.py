"""Tests for the mode context bar Qt translation path."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QPushButton, QToolButton, QWidget
from pytestqt.qtbot import QtBot

from chappy.gui.shell.mode_context_bar import ModeContextBar
from chappy.gui.shell.shortcuts import format_runtime_shortcuts
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate

TOOLBAR_TEXT_SOURCES = {
    "New": "新規",
    "Open": "開く",
    "Save": "保存",
    "Undo": "元に戻す",
    "Redo": "やり直す",
}
TOOLBAR_TOOLTIP_SOURCES = {
    "Load observed flux and error FITS files": "観測フラックスと誤差のFITSを読み込みます",
    "Open project ({open_project_shortcut})": ("プロジェクトを開く ({open_project_shortcut})"),
    "Save project ({save_project_shortcut})": ("プロジェクトを保存 ({save_project_shortcut})"),
    "Undo last action ({undo_shortcut})": "直前の操作を取り消し ({undo_shortcut})",
    "Redo last undone action ({redo_shortcut})": (
        "最後に取り消した操作をやり直し ({redo_shortcut})"
    ),
}
MODE_TEXT_SOURCES = {"Identify": "同定", "Analysis": "解析", "Continuum": "連続光"}
MODE_TOOLTIP_SOURCES = {
    "Identify mode": "同定モード",
    "Analysis workspace": "解析ワークスペース",
    "Continuum editing mode": "連続光編集モード",
}
ZOOM_TEXT_SOURCES = {
    "Zoom": "ズーム",
    "Click and drag to zoom to selected area": "ドラッグで選択範囲を拡大",
    "Rectangle zoom mode active - Click again to disable": (
        "矩形ズームモードが有効 - もう一度クリックで解除"
    ),
}

MODE_CONTEXT_BAR_SOURCES = (
    set(TOOLBAR_TEXT_SOURCES)
    | set(TOOLBAR_TOOLTIP_SOURCES)
    | set(MODE_TEXT_SOURCES)
    | set(MODE_TOOLTIP_SOURCES)
    | set(ZOOM_TEXT_SOURCES)
)


def _show_bar(bar: ModeContextBar, qtbot: QtBot) -> None:
    """Show the mode context bar before language-change assertions.

    Args:
        bar: Mode context bar under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    qtbot.addWidget(bar)
    bar.show()
    qtbot.waitUntil(bar.isVisible, timeout=1000)


def _tool_button(bar: ModeContextBar, object_name: str) -> QToolButton:
    """Return a named tool button from the mode context bar.

    Args:
        bar: Mode context bar under test.
        object_name: Qt object name assigned to the tool button.

    Returns:
        Matching tool button.
    """
    button = bar.findChild(QToolButton, object_name)
    assert button is not None
    return button


def _mode_button(bar: ModeContextBar, object_name: str) -> QPushButton:
    """Return a named mode button from the mode context bar.

    Args:
        bar: Mode context bar under test.
        object_name: Qt object name assigned to the mode button.

    Returns:
        Matching push button.
    """
    button = bar.findChild(QPushButton, object_name)
    assert button is not None
    return button


def _write_mode_context_bar_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for ModeContextBar.

    Args:
        ts_path: Output TS file path.
    """
    ts = ET.Element("TS", version="2.1", language="ja_JP")
    context = ET.SubElement(ts, "context")
    name = ET.SubElement(context, "name")
    name.text = "ModeContextBar"
    translations = {
        **TOOLBAR_TEXT_SOURCES,
        **TOOLBAR_TOOLTIP_SOURCES,
        **MODE_TEXT_SOURCES,
        **MODE_TOOLTIP_SOURCES,
        **ZOOM_TEXT_SOURCES,
    }
    for source_text, translation_text in translations.items():
        message = ET.SubElement(context, "message")
        source = ET.SubElement(message, "source")
        source.text = source_text
        translation = ET.SubElement(message, "translation")
        translation.text = translation_text
    tree = ET.ElementTree(ts)
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)


def _compile_mode_context_bar_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for ModeContextBar.

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
    _write_mode_context_bar_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled context-bar catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_mode_context_bar_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


def test_initial_button_texts_use_qt_sources(qtbot: QtBot) -> None:
    """Verify initial ModeContextBar display text uses Qt source strings."""
    bar = ModeContextBar()
    _show_bar(bar, qtbot)

    assert _tool_button(bar, "modeContextBar_open_observation_data").text() == "📄 New"
    assert _tool_button(bar, "modeContextBar_open_project").text() == "📂 Open"
    assert _tool_button(bar, "modeContextBar_save_project").text() == "💾 Save"
    assert _tool_button(bar, "modeContextBar_undo").text() == "↶ Undo"
    assert _tool_button(bar, "modeContextBar_redo").text() == "↷ Redo"
    assert _tool_button(bar, "modeContextBar_zoom_rect").text() == "🔍 Zoom"
    assert _mode_button(bar, "modeButton_IDENTIFY").text() == "🔍 Identify"
    assert _mode_button(bar, "modeButton_ANALYSIS").text() == "⚙️ Analysis"
    assert _mode_button(bar, "modeButton_CONTINUUM").text() == "〰 Continuum"
    assert [
        button.objectName()
        for button in bar.findChildren(QPushButton)
        if button.objectName().startswith("modeButton_")
    ] == ["modeButton_IDENTIFY", "modeButton_ANALYSIS", "modeButton_CONTINUUM"]

    assert (
        _tool_button(bar, "modeContextBar_open_observation_data").toolTip()
        == "Load observed flux and error FITS files"
    )
    assert _tool_button(bar, "modeContextBar_zoom_rect").toolTip() == (
        "Click and drag to zoom to selected area"
    )


def test_qt_translator_updates_existing_context_bar(
    qtbot: QtBot, qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Verify an existing ModeContextBar updates after Qt language changes."""
    bar = ModeContextBar()
    _show_bar(bar, qtbot)

    zoom_button = _tool_button(bar, "modeContextBar_zoom_rect")
    zoom_button.setChecked(True)

    state = qt_translator_installer.install_language("ja")

    assert state.app_translator_loaded
    qtbot.waitUntil(lambda: _tool_button(bar, "modeContextBar_open_project").text() == "📂 開く")
    assert _tool_button(bar, "modeContextBar_open_observation_data").text() == "📄 新規"
    assert _tool_button(bar, "modeContextBar_save_project").text() == "💾 保存"
    assert _tool_button(bar, "modeContextBar_undo").text() == "↶ 元に戻す"
    assert _tool_button(bar, "modeContextBar_redo").text() == "↷ やり直す"
    assert _tool_button(bar, "modeContextBar_open_project").toolTip() == (
        format_runtime_shortcuts("プロジェクトを開く ({open_project_shortcut})")
    )
    assert zoom_button.text() == "🔲 ズーム"
    assert zoom_button.toolTip() == "矩形ズームモードが有効 - もう一度クリックで解除"
    assert _mode_button(bar, "modeButton_IDENTIFY").text() == "🔍 同定"
    assert _mode_button(bar, "modeButton_ANALYSIS").text() == "⚙️ 解析"
    assert _mode_button(bar, "modeButton_CONTINUUM").text() == "〰 連続光"
    assert _mode_button(bar, "modeButton_ANALYSIS").toolTip() == "解析ワークスペース"

    qt_translator_installer.install_language("en")
    qtbot.waitUntil(lambda: _tool_button(bar, "modeContextBar_open_project").text() == "📂 Open")
    assert zoom_button.text() == "🔲 Zoom"
    assert zoom_button.toolTip() == "Rectangle zoom mode active - Click again to disable"


def test_mode_selector_is_content_width_segmented_control(qtbot: QtBot) -> None:
    """Verify mode navigation is rendered as one content-width control."""
    bar = ModeContextBar()
    bar.resize(1024, bar.sizeHint().height())
    _show_bar(bar, qtbot)

    container = bar.findChild(QFrame, "modeSegmentedControl")
    assert container is not None
    layout = container.layout()
    assert layout is not None
    assert layout.spacing() == 1
    margins = layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 0, 0, 0)

    buttons = [
        _mode_button(bar, "modeButton_IDENTIFY"),
        _mode_button(bar, "modeButton_ANALYSIS"),
        _mode_button(bar, "modeButton_CONTINUUM"),
    ]
    assert [button.property("segmentPosition") for button in buttons] == [
        "first",
        "middle",
        "last",
    ]
    assert len({button.height() for button in buttons}) == 1
    assert all(button.width() >= button.sizeHint().width() for button in buttons)


def test_mode_description_uses_transparent_background(qtbot: QtBot) -> None:
    """Keep the non-interactive mode description visually distinct from controls."""
    bar = ModeContextBar()
    _show_bar(bar, qtbot)

    info_group = bar.findChild(QWidget, "modeContextBar_infoGroup")
    assert info_group is not None
    assert not info_group.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert not info_group.autoFillBackground()


def test_compact_context_bar_keeps_mode_labels(qtbot: QtBot) -> None:
    """Verify narrow layouts compact tools without hiding mode identity."""
    bar = ModeContextBar()
    _show_bar(bar, qtbot)
    bar._apply_tool_presentation(icon_only=True)

    assert _tool_button(bar, "modeContextBar_open_project").text() == "📂"
    assert _mode_button(bar, "modeButton_IDENTIFY").text() == "🔍 Identify"
    assert _mode_button(bar, "modeButton_ANALYSIS").text() == "⚙️ Analysis"
    assert _mode_button(bar, "modeButton_CONTINUUM").text() == "〰 Continuum"


def test_lupdate_extracts_mode_context_bar_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated ModeContextBar sources without old keys."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(source_dirs=[Path("src/chappy/gui/shell/mode_context_bar.py")], ts_output=ts_path)

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert sources == MODE_CONTEXT_BAR_SOURCES
    assert not any("GUI__" in source for source in sources)
