"""Tests for the mode panel host container."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QSplitter, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot

from chappy.core.editing_mode import EditingMode
from chappy.gui.modes.mode_panel_host import ModeSidePanelHost
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate

START_PLACEHOLDER_SOURCE = "Open observation data or a project to see tools here."
GENERIC_PLACEHOLDER_SOURCE = "No side panel available for this mode."
START_PLACEHOLDER_JA = "観測データまたはプロジェクトを開くと、ここにツールが表示されます。"
GENERIC_PLACEHOLDER_JA = "このモードで利用できるサイドパネルはありません。"


def _placeholder_label(panel: ModeSidePanelHost) -> QLabel:
    """Return the placeholder text label from the side panel.

    Args:
        panel: Side panel under test.

    Returns:
        Placeholder label.
    """
    label = panel.findChild(QLabel)
    assert label is not None
    return label


def _show_panel(panel: ModeSidePanelHost, qtbot: QtBot) -> None:
    """Show the side panel and wait until Qt marks it visible.

    Args:
        panel: Side panel under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitUntil(panel.isVisible, timeout=1000)


def _write_mode_panel_host_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for ModeSidePanelHost.

    Args:
        ts_path: Output TS file path.
    """
    ts = ET.Element("TS", version="2.1", language="ja_JP")
    context = ET.SubElement(ts, "context")
    name = ET.SubElement(context, "name")
    name.text = "ModeSidePanelHost"
    translations = {
        START_PLACEHOLDER_SOURCE: START_PLACEHOLDER_JA,
        GENERIC_PLACEHOLDER_SOURCE: GENERIC_PLACEHOLDER_JA,
    }
    for source_text, translation_text in translations.items():
        message = ET.SubElement(context, "message")
        source = ET.SubElement(message, "source")
        source.text = source_text
        translation = ET.SubElement(message, "translation")
        translation.text = translation_text
    tree = ET.ElementTree(ts)
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)


def _compile_mode_panel_host_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for ModeSidePanelHost.

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
    _write_mode_panel_host_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled side-panel test catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_mode_panel_host_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


def test_activate_mode_none_shows_start_placeholder(qtbot: QtBot) -> None:
    """Verify None mode keeps the start placeholder behavior."""
    panel = ModeSidePanelHost()
    _show_panel(panel, qtbot)

    panel.activate_mode(None)

    assert _placeholder_label(panel).text() in {START_PLACEHOLDER_SOURCE, START_PLACEHOLDER_JA}
    assert panel._stack.currentIndex() == panel._placeholder_index


def test_unregistered_mode_raises(qtbot: QtBot) -> None:
    """Verify an unregistered non-start mode fails fast."""
    panel = ModeSidePanelHost()
    _show_panel(panel, qtbot)

    with pytest.raises(RuntimeError, match="No side panel registered"):
        panel.activate_mode(EditingMode.ANALYSIS)


def test_registered_mode_shows_registered_panel(qtbot: QtBot) -> None:
    """Verify a registered mode still displays its panel."""
    panel = ModeSidePanelHost()
    registered_panel = QWidget()
    _show_panel(panel, qtbot)

    panel.register_panel(EditingMode.ANALYSIS, registered_panel)
    panel.activate_mode(EditingMode.ANALYSIS)

    assert panel._stack.currentWidget() is registered_panel
    assert registered_panel.objectName() == "modeSidePanel_analysis"


def test_minimum_size_hint_tracks_only_the_active_page(qtbot: QtBot) -> None:
    """Hidden wide pages must not prevent a compact active page from shrinking."""
    panel = ModeSidePanelHost()
    content_sized_page = QWidget()
    content_layout = QVBoxLayout(content_sized_page)
    content_layout.addWidget(QLabel("Content-derived minimum width " * 4))
    compact_page = QWidget()
    compact_page.setMinimumWidth(220)
    panel.register_panel(EditingMode.IDENTIFY, content_sized_page)
    panel.register_panel(EditingMode.ANALYSIS, compact_page)
    qtbot.addWidget(panel)

    panel.activate_mode(EditingMode.IDENTIFY)
    content_minimum = content_sized_page.minimumSizeHint().expandedTo(
        content_sized_page.minimumSize()
    )
    assert panel.minimumSizeHint() == content_minimum

    panel.activate_mode(EditingMode.ANALYSIS)
    assert panel.minimumWidth() == 0
    assert panel.minimumSizeHint().width() == 220
    assert panel.minimumSizeHint().width() < content_minimum.width()


def test_splitter_enforces_current_page_minimum_after_mode_change(qtbot: QtBot) -> None:
    """A splitter squeeze must respect the active page and release the hidden page width."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    left = QWidget()
    left.setMinimumWidth(80)
    panel = ModeSidePanelHost()
    wide_page = QWidget()
    wide_page.setMinimumWidth(400)
    compact_page = QWidget()
    compact_page.setMinimumWidth(220)
    panel.register_panel(EditingMode.IDENTIFY, wide_page)
    panel.register_panel(EditingMode.ANALYSIS, compact_page)
    splitter.addWidget(left)
    splitter.addWidget(panel)
    splitter.resize(900, 400)
    qtbot.addWidget(splitter)
    splitter.show()
    qtbot.waitUntil(splitter.isVisible, timeout=1000)

    panel.activate_mode(EditingMode.IDENTIFY)
    splitter.setSizes([850, 50])
    QApplication.processEvents()
    assert panel.width() >= 400

    panel.activate_mode(EditingMode.ANALYSIS)
    splitter.setSizes([850, 50])
    QApplication.processEvents()
    assert 220 <= panel.width() < 400


def test_qt_translator_updates_existing_placeholder(
    qtbot: QtBot, qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Verify an existing placeholder updates after Qt language changes."""
    panel = ModeSidePanelHost()
    _show_panel(panel, qtbot)
    label = _placeholder_label(panel)

    panel.activate_mode(None)
    assert label.text() in {START_PLACEHOLDER_SOURCE, START_PLACEHOLDER_JA}

    state = qt_translator_installer.install_language("ja")
    assert state.app_translator_loaded
    qtbot.waitUntil(lambda: label.text() == START_PLACEHOLDER_JA, timeout=1000)

    qt_translator_installer.install_language("en")
    qtbot.waitUntil(
        lambda: label.text() in {START_PLACEHOLDER_SOURCE, START_PLACEHOLDER_JA}, timeout=1000
    )


def test_lupdate_extracts_mode_panel_host_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts the migrated ModeSidePanelHost placeholder sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(source_dirs=[Path("src/chappy/gui/modes/mode_panel_host.py")], ts_output=ts_path)

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert sources == {START_PLACEHOLDER_SOURCE, GENERIC_PLACEHOLDER_SOURCE}
    assert not any("GUI__" in source for source in sources)
