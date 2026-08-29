"""Tests for the start mode drag-and-drop overlay."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QWidget

from chappy.gui.common.start_mode_overlay import StartModeOverlay
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate

MAIN_DROP_HINT_SOURCE = "Drop files here"
SECONDARY_DROP_HINT_SOURCE = "or use New / Open"
SUPPORTED_FORMATS_SOURCE = "FITS (flux + error)\nProject (.h5 or .hdf5)"
MAIN_DROP_HINT_JA = "ファイルをドロップ"
SECONDARY_DROP_HINT_JA = "または［新規］／［開く］"
SUPPORTED_FORMATS_JA = "FITS（フラックス＋誤差）\nプロジェクト（.h5・.hdf5）"


def _show_overlay(overlay: StartModeOverlay, qtbot: QtBot) -> None:
    """Show the overlay and wait until Qt marks it visible.

    Args:
        overlay: Overlay under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    qtbot.addWidget(overlay)
    overlay.show()
    qtbot.waitUntil(overlay.isVisible, timeout=1000)


def _write_start_mode_overlay_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for StartModeOverlay.

    Args:
        ts_path: Output TS file path.
    """
    ts = ET.Element("TS", version="2.1", language="ja_JP")
    context = ET.SubElement(ts, "context")
    name = ET.SubElement(context, "name")
    name.text = "StartModeOverlay"
    translations = {
        MAIN_DROP_HINT_SOURCE: MAIN_DROP_HINT_JA,
        SECONDARY_DROP_HINT_SOURCE: SECONDARY_DROP_HINT_JA,
        SUPPORTED_FORMATS_SOURCE: SUPPORTED_FORMATS_JA,
    }
    for source_text, translation_text in translations.items():
        message = ET.SubElement(context, "message")
        source = ET.SubElement(message, "source")
        source.text = source_text
        translation = ET.SubElement(message, "translation")
        translation.text = translation_text
    tree = ET.ElementTree(ts)
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)


def _compile_start_mode_overlay_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for StartModeOverlay.

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
    _write_start_mode_overlay_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled overlay test catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_start_mode_overlay_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


def test_default_drop_hints_use_english_sources(qtbot: QtBot) -> None:
    """Verify the overlay uses Qt source text without an installed translator."""
    overlay = StartModeOverlay()
    _show_overlay(overlay, qtbot)

    assert overlay._main_label.text() == MAIN_DROP_HINT_SOURCE
    assert overlay._secondary_label.text() == SECONDARY_DROP_HINT_SOURCE
    assert overlay._formats_label.text() == SUPPORTED_FORMATS_SOURCE
    assert overlay._secondary_label.isVisible()


def test_qt_translator_updates_existing_drop_hints(
    qtbot: QtBot, qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Verify existing labels update from Qt LanguageChange events."""
    overlay = StartModeOverlay()
    _show_overlay(overlay, qtbot)

    state = qt_translator_installer.install_language("ja")

    assert state.app_translator_loaded
    qtbot.waitUntil(lambda: overlay._main_label.text() == MAIN_DROP_HINT_JA, timeout=1000)
    assert overlay._secondary_label.text() == SECONDARY_DROP_HINT_JA
    assert overlay._formats_label.text() == SUPPORTED_FORMATS_JA

    qt_translator_installer.install_language("en")
    qtbot.waitUntil(lambda: overlay._main_label.text() == MAIN_DROP_HINT_SOURCE, timeout=1000)
    assert overlay._secondary_label.text() == SECONDARY_DROP_HINT_SOURCE
    assert overlay._formats_label.text() == SUPPORTED_FORMATS_SOURCE


class _DropTarget(QWidget):
    """Record forwarded drag-and-drop events."""

    def __init__(self) -> None:
        """Initialize recorded event names."""
        super().__init__()
        self.events: list[str] = []

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Record drag-enter forwarding."""
        self.events.append("dragEnterEvent")
        event.accept()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Record drag-move forwarding."""
        self.events.append("dragMoveEvent")

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Record drag-leave forwarding."""
        self.events.append("dragLeaveEvent")

    def dropEvent(self, event: QDropEvent) -> None:
        """Record drop forwarding."""
        self.events.append("dropEvent")


def test_start_mode_overlay_forwards_drag_events_to_explicit_target(qtbot: QtBot) -> None:
    """Drag events should use the explicit target instead of probing the parent window."""
    target = _DropTarget()
    overlay = StartModeOverlay(drop_target=target)
    _show_overlay(overlay, qtbot)
    event = QDragEnterEvent(
        QPoint(0, 0),
        Qt.DropAction.CopyAction,
        QMimeData(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    overlay.dragEnterEvent(event)

    assert target.events == ["dragEnterEvent"]


def test_lupdate_extracts_start_mode_overlay_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts the migrated StartModeOverlay sources only."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/common/start_mode_overlay.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert sources == {MAIN_DROP_HINT_SOURCE, SECONDARY_DROP_HINT_SOURCE, SUPPORTED_FORMATS_SOURCE}
    assert not any("GUI__" in source for source in sources)
