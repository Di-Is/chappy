"""Tests for the data control panel."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QToolButton, QWidget
from pytestqt.qtbot import QtBot

from chappy.gui.shell.data_control_panel import DataControlPanel, RangeValues
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate

WAVELENGTH_HEADER_SOURCE = "Wavelength (Å)"
FLUX_HEADER_SOURCE = "Flux"
MIN_SOURCE = "Min"
MAX_SOURCE = "Max"
RESET_VIEW_SOURCE = "Reset View"
AUTO_ADJUST_SOURCE = "Auto Adjust"
DISPLAY_SOURCE = "Display"

WAVELENGTH_HEADER_JA = "波長 (Å)"
FLUX_HEADER_JA = "フラックス"
MIN_JA = "最小"
MAX_JA = "最大"
RESET_VIEW_JA = "表示をリセット"
AUTO_ADJUST_JA = "自動調整"

DATA_CONTROL_SOURCES = {
    WAVELENGTH_HEADER_SOURCE,
    FLUX_HEADER_SOURCE,
    MIN_SOURCE,
    MAX_SOURCE,
    RESET_VIEW_SOURCE,
    AUTO_ADJUST_SOURCE,
    DISPLAY_SOURCE,
}


def _label(panel: DataControlPanel, object_name: str) -> QLabel:
    """Return a named label from the data control panel.

    Args:
        panel: Data control panel under test.
        object_name: Qt object name assigned to the label.

    Returns:
        Matching label.
    """
    label = panel.findChild(QLabel, object_name)
    assert label is not None
    return label


def _button(panel: DataControlPanel, object_name: str) -> QPushButton:
    """Return a named button from the data control panel.

    Args:
        panel: Data control panel under test.
        object_name: Qt object name assigned to the button.

    Returns:
        Matching button.
    """
    button = panel.findChild(QPushButton, object_name)
    assert button is not None
    return button


def _field(panel: DataControlPanel, object_name: str) -> QLineEdit:
    """Return a named line edit from the data control panel.

    Args:
        panel: Data control panel under test.
        object_name: Qt object name assigned to the field.

    Returns:
        Matching line edit.
    """
    field = panel.findChild(QLineEdit, object_name)
    assert field is not None
    return field


def _show_panel(panel: DataControlPanel, qtbot: QtBot) -> None:
    """Show the data control panel before language-change assertions.

    Args:
        panel: Data control panel under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    qtbot.addWidget(panel)
    panel.show()
    qtbot.waitUntil(panel.isVisible, timeout=1000)


def _panel_texts(panel: DataControlPanel) -> dict[str, str]:
    """Collect translated text from the data control panel.

    Args:
        panel: Data control panel under test.

    Returns:
        Text keyed by stable widget role.
    """
    return {
        "wavelength_header": _label(panel, "dataControlPanel_wavelengthHeaderLabel").text(),
        "flux_header": _label(panel, "dataControlPanel_fluxHeaderLabel").text(),
        "wavelength_min": _label(panel, "dataControlPanel_wavelengthMinLabel").text(),
        "wavelength_max": _label(panel, "dataControlPanel_wavelengthMaxLabel").text(),
        "flux_min": _label(panel, "dataControlPanel_fluxMinLabel").text(),
        "flux_max": _label(panel, "dataControlPanel_fluxMaxLabel").text(),
        "reset_view": _button(panel, "resetViewButton").text(),
        "auto_adjust": _button(panel, "autoAdjustButton").text(),
    }


def _write_data_control_panel_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for DataControlPanel.

    Args:
        ts_path: Output TS file path.
    """
    ts = ET.Element("TS", version="2.1", language="ja_JP")
    context = ET.SubElement(ts, "context")
    name = ET.SubElement(context, "name")
    name.text = "DataControlPanel"
    translations = {
        WAVELENGTH_HEADER_SOURCE: WAVELENGTH_HEADER_JA,
        FLUX_HEADER_SOURCE: FLUX_HEADER_JA,
        MIN_SOURCE: MIN_JA,
        MAX_SOURCE: MAX_JA,
        RESET_VIEW_SOURCE: RESET_VIEW_JA,
        AUTO_ADJUST_SOURCE: AUTO_ADJUST_JA,
    }
    for source_text, translation_text in translations.items():
        message = ET.SubElement(context, "message")
        source = ET.SubElement(message, "source")
        source.text = source_text
        translation = ET.SubElement(message, "translation")
        translation.text = translation_text
    tree = ET.ElementTree(ts)
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)


def _compile_data_control_panel_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for DataControlPanel.

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
    _write_data_control_panel_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled data-panel catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_data_control_panel_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


def test_initial_labels_use_qt_source_text(qtbot: QtBot) -> None:
    """Verify initial display text uses Qt source strings."""
    panel = DataControlPanel()
    _show_panel(panel, qtbot)

    assert _panel_texts(panel) == {
        "wavelength_header": WAVELENGTH_HEADER_SOURCE,
        "flux_header": FLUX_HEADER_SOURCE,
        "wavelength_min": MIN_SOURCE,
        "wavelength_max": MAX_SOURCE,
        "flux_min": MIN_SOURCE,
        "flux_max": MAX_SOURCE,
        "reset_view": RESET_VIEW_SOURCE,
        "auto_adjust": AUTO_ADJUST_SOURCE,
    }


def test_display_menu_button_precedes_reset_view_and_keeps_action_order(qtbot: QtBot) -> None:
    """The attached Display menu sits before Reset View and preserves action order."""
    panel = DataControlPanel()
    _show_panel(panel, qtbot)
    error_action = QAction("Error spectrum", panel)
    component_action = QAction("Component profiles", panel)

    panel.attach_display_menu((error_action, component_action))

    button = panel.findChild(QToolButton, "displayMenuButton")
    assert button is not None
    assert button.text() == DISPLAY_SOURCE
    menu = button.menu()
    assert menu is not None
    assert list(menu.actions()) == [error_action, component_action]

    button_group = panel.findChild(QWidget, "dataControlPanel_buttonGroup")
    assert button_group is not None
    layout = button_group.layout()
    assert layout is not None
    assert layout.indexOf(button) < layout.indexOf(_button(panel, "resetViewButton"))


def test_range_fields_start_pending_until_ranges_are_loaded(qtbot: QtBot) -> None:
    """Verify range fields do not expose plausible current state before data is loaded."""
    panel = DataControlPanel()
    _show_panel(panel, qtbot)

    wavelength_min = _field(panel, "dataControlPanel_wavelengthMinField")
    wavelength_max = _field(panel, "dataControlPanel_wavelengthMaxField")
    flux_min = _field(panel, "dataControlPanel_fluxMinField")
    flux_max = _field(panel, "dataControlPanel_fluxMaxField")
    reset_button = _button(panel, "resetViewButton")
    auto_adjust_button = _button(panel, "autoAdjustButton")

    assert wavelength_min.text() == ""
    assert wavelength_max.text() == ""
    assert flux_min.text() == ""
    assert flux_max.text() == ""
    assert not wavelength_min.isEnabled()
    assert not wavelength_max.isEnabled()
    assert not flux_min.isEnabled()
    assert not flux_max.isEnabled()
    assert not reset_button.isEnabled()
    assert not auto_adjust_button.isEnabled()

    panel.update_ranges(RangeValues(4100.0, 4200.0, -0.2, 1.4))

    assert wavelength_min.text() == "4100.00"
    assert wavelength_max.text() == "4200.00"
    assert flux_min.text() == "-0.20"
    assert flux_max.text() == "1.40"
    assert wavelength_min.isEnabled()
    assert wavelength_max.isEnabled()
    assert flux_min.isEnabled()
    assert flux_max.isEnabled()
    assert reset_button.isEnabled()
    assert auto_adjust_button.isEnabled()

    panel.clear_ranges()

    assert wavelength_min.text() == ""
    assert wavelength_max.text() == ""
    assert flux_min.text() == ""
    assert flux_max.text() == ""
    assert not wavelength_min.isEnabled()
    assert not wavelength_max.isEnabled()
    assert not flux_min.isEnabled()
    assert not flux_max.isEnabled()
    assert not reset_button.isEnabled()
    assert not auto_adjust_button.isEnabled()


def test_update_ranges_rejects_invalid_range_state(qtbot: QtBot) -> None:
    """Malformed range state should fail fast before it can drive the panel."""
    panel = DataControlPanel()
    _show_panel(panel, qtbot)

    with pytest.raises(ValueError, match="Wavelength range"):
        panel.update_ranges(RangeValues(4200.0, 4100.0, -0.2, 1.4))

    with pytest.raises(ValueError, match="Flux range"):
        panel.update_ranges(RangeValues(4100.0, 4200.0, 1.4, -0.2))

    with pytest.raises(ValueError, match="finite"):
        panel.update_ranges(RangeValues(4100.0, float("nan"), -0.2, 1.4))


def test_invalid_numeric_text_reverts_without_emitting_range(qtbot: QtBot) -> None:
    """Invalid field text should recover visibly instead of being silently ignored."""
    panel = DataControlPanel()
    _show_panel(panel, qtbot)
    panel.update_ranges(RangeValues(4100.0, 4200.0, -0.2, 1.4))
    emissions: list[tuple[float, float]] = []
    wavelength_min = _field(panel, "dataControlPanel_wavelengthMinField")

    wavelength_min.setFocus()
    wavelength_min.setText("")
    assert wavelength_min.text() == ""
    panel.wavelength_range_applied.connect(lambda lower, upper: emissions.append((lower, upper)))
    qtbot.keyClick(wavelength_min, Qt.Key.Key_Return)

    assert emissions == []
    assert wavelength_min.text() == "4100.00"


def test_domain_invalid_range_reverts_without_emitting_range(qtbot: QtBot) -> None:
    """Domain-invalid range edits should restore the last accepted values."""
    panel = DataControlPanel()
    _show_panel(panel, qtbot)
    panel.update_ranges(RangeValues(4100.0, 4200.0, -0.2, 1.4))
    wavelength_emissions: list[tuple[float, float]] = []
    flux_emissions: list[tuple[float, float]] = []
    wavelength_min = _field(panel, "dataControlPanel_wavelengthMinField")
    flux_max = _field(panel, "dataControlPanel_fluxMaxField")
    panel.wavelength_range_applied.connect(
        lambda lower, upper: wavelength_emissions.append((lower, upper))
    )
    panel.flux_range_applied.connect(lambda lower, upper: flux_emissions.append((lower, upper)))

    wavelength_min.setFocus()
    wavelength_min.setText("4300.00")
    qtbot.keyClick(wavelength_min, Qt.Key.Key_Return)

    assert wavelength_emissions == []
    assert wavelength_min.text() == "4100.00"

    flux_max.setFocus()
    flux_max.setText("-0.30")
    qtbot.keyClick(flux_max, Qt.Key.Key_Return)

    assert flux_emissions == []
    assert flux_max.text() == "1.40"


def test_qt_translator_updates_existing_panel_text(
    qtbot: QtBot, qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Verify an existing data control panel updates after Qt language changes."""
    panel = DataControlPanel()
    _show_panel(panel, qtbot)

    state = qt_translator_installer.install_language("ja")
    assert state.app_translator_loaded
    qtbot.waitUntil(
        lambda: (
            _panel_texts(panel)
            == {
                "wavelength_header": WAVELENGTH_HEADER_JA,
                "flux_header": FLUX_HEADER_JA,
                "wavelength_min": MIN_JA,
                "wavelength_max": MAX_JA,
                "flux_min": MIN_JA,
                "flux_max": MAX_JA,
                "reset_view": RESET_VIEW_JA,
                "auto_adjust": AUTO_ADJUST_JA,
            }
        ),
        timeout=1000,
    )

    qt_translator_installer.install_language("en")
    qtbot.waitUntil(
        lambda: (
            _panel_texts(panel)
            == {
                "wavelength_header": WAVELENGTH_HEADER_SOURCE,
                "flux_header": FLUX_HEADER_SOURCE,
                "wavelength_min": MIN_SOURCE,
                "wavelength_max": MAX_SOURCE,
                "flux_min": MIN_SOURCE,
                "flux_max": MAX_SOURCE,
                "reset_view": RESET_VIEW_SOURCE,
                "auto_adjust": AUTO_ADJUST_SOURCE,
            }
        ),
        timeout=1000,
    )


def test_lupdate_extracts_data_control_panel_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated DataControlPanel sources without old keys."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/shell/data_control_panel.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert sources == DATA_CONTROL_SOURCES
    assert not any("GUI__" in source for source in sources)
