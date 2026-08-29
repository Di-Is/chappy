"""Tests for RegionDetailPanel column definition single-source policy."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QTreeWidget

from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor
from chappy.gui.modes.analysis.region_detail.panel import RegionDetailPanel
from tests.gui.support.faithful_env import faithful_application_environment
from tests.gui.widgets.optimize_panel_helpers import (
    AnalysisFocusRecorder,
    NoOpModelAdditionUseCase,
    build_region_detail_usecases,
)
from chappy.i18n.qt_translator import QtTranslatorInstaller
from scripts.i18n_lrelease import run_lrelease
from scripts.i18n_lupdate import run_lupdate


if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


HEADER_SOURCES = (
    "ID",
    "Species",
    "z",
    "logN",
    "b",
    "Cf",
    "Analysis range [km/s]",
    "λ [Å]",
    "Lookback time [Gyr]",
    "Comoving distance [Mpc]",
)

HEADER_TRANSLATIONS_JA = (
    "ID",
    "線種",
    "z",
    "logN",
    "b",
    "Cf",
    "解析範囲 [km/s]",
    "中心波長 [Å]",
    "ルックバックタイム [Gyr]",
    "共動距離 [Mpc]",
)
VELOCITY_CONTEXT_MENU_SOURCE = "Add Component Here"
PANEL_SOURCES = (
    "Select region",
    "Needs Optimization",
    "Run fit",
    "Run a fit to see results here.",
    "Export Results",
    "Export optimized results as CSV",
    "Add Component…",
    "Add Component",
    "Add a model component to {name}",
    "Results",
    "Status",
    "Fit result",
    "Components",
    "Not fitted",
    "Fitted",
    "The region structure changed; run the fit again to refresh results.",
    "Mask editing is disabled in velocity",
    "Redshift must be between {z_min:.3f} and {z_max:.3f} for this line",
    "Enter a valid value for this parameter",
    "Fix {parameter}",
    "Adjust parameters...",
    "Delete Component",
    "CSV UTF-8 (*.csv)",
    "CSV UTF-8 BOM - Excel (*.csv)",
    "CSV Files (*.csv)",
    "Error",
    "Masked Range",
    "Cannot add a masked range because no regions exist.",
    "Confirm",
    "Do you want to delete this component?",
    "Delete {count} components?",
    "Export optimization results",
    "No regions",
    "Optimizing…",
    "χ² = {value:.3f}",
    "χ²ν = {value:.3f}",
    "Optimization failed",
    "Load a spectrum to enable fitting.",
    "Select a region to enable fitting.",
    "Add a model component to this region to enable fitting.",
    "Optimizing...",
    "Exported CSV to {path}",
    "Failed to export results: {error}",
)


def _create_panel(qtbot: "QtBot") -> RegionDetailPanel:
    """Create and register a region-detail panel."""
    parameter_mutation_usecase, tie_set_edit_usecase = build_region_detail_usecases()
    widget = RegionDetailPanel(
        optimize_editor=OptimizeEditor(),
        analysis_focus=AnalysisFocusRecorder(),
        model_addition_usecase=NoOpModelAdditionUseCase(),
        parameter_mutation_usecase=parameter_mutation_usecase,
        tie_set_edit_usecase=tie_set_edit_usecase,
        velocity_plot_active_provider=lambda: False,
        project_file_path_provider=lambda: None,
    )
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def panel(qtbot: "QtBot") -> RegionDetailPanel:
    """Create an optimize panel for column contract tests."""
    return _create_panel(qtbot)


def _tree(panel: RegionDetailPanel) -> QTreeWidget:
    """Return the optimize parameter tree.

    Args:
        panel: Optimize mode panel under test.

    Returns:
        Parameter tree widget.
    """
    tree = panel.findChild(QTreeWidget, "analysisDetailParameterTree")
    assert tree is not None
    return tree


def _header_texts(panel: RegionDetailPanel) -> tuple[str, ...]:
    """Collect optimize table header text.

    Args:
        panel: Optimize mode panel under test.

    Returns:
        Header texts in display order.
    """
    tree = _tree(panel)
    header = tree.headerItem()
    return tuple(header.text(index) for index in range(tree.columnCount()))


def _show_panel(panel: RegionDetailPanel, qtbot: "QtBot") -> None:
    """Show the optimize panel before language-change assertions.

    Args:
        panel: Optimize mode panel under test.
        qtbot: pytest-qt bot used to manage the widget.
    """
    panel.show()
    qtbot.waitUntil(panel.isVisible, timeout=1000)


def _write_optimize_headers_ja_ts(ts_path: Path) -> None:
    """Write a minimal Japanese TS catalog for optimize table headers.

    Args:
        ts_path: Output TS file path.
    """
    ts = ET.Element("TS", version="2.1", language="ja_JP")
    context = ET.SubElement(ts, "context")
    name = ET.SubElement(context, "name")
    name.text = "RegionDetailPanel"
    for source_text, translation_text in zip(HEADER_SOURCES, HEADER_TRANSLATIONS_JA):
        message = ET.SubElement(context, "message")
        source = ET.SubElement(message, "source")
        source.text = source_text
        translation = ET.SubElement(message, "translation")
        translation.text = translation_text
    tree = ET.ElementTree(ts)
    tree.write(ts_path, encoding="utf-8", xml_declaration=True)


def _compile_optimize_headers_ja_qm(tmp_path: Path) -> Path:
    """Compile a test Japanese QM catalog for optimize table headers.

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
    _write_optimize_headers_ja_ts(ts_path)
    run_lrelease(ts_input=ts_path, qm_output=qm_path)
    return catalog_root


@pytest.fixture()
def qt_translator_installer(tmp_path: Path) -> Iterator[QtTranslatorInstaller]:
    """Provide a translator installer with a compiled optimize-header catalog.

    Args:
        tmp_path: Temporary directory for generated catalogs.

    Yields:
        Translator installer configured with the test catalog root.
    """
    catalog_root = _compile_optimize_headers_ja_qm(tmp_path)
    installer = QtTranslatorInstaller(
        translation_root=catalog_root, qt_translation_root=tmp_path / "missing_qt_catalogs"
    )
    yield installer
    installer.remove_translators()


class TestTreeColumnCount:
    """Tests for tree widget column count consistency."""

    def test_column_count_matches_column_keys(self, panel: RegionDetailPanel) -> None:
        """Rendered tree column count should match the public column contract."""
        assert _tree(panel).columnCount() == len(HEADER_SOURCES)


def test_headers_use_qt_source_text(panel: RegionDetailPanel) -> None:
    """Headers should use Qt source strings matching existing English YAML."""
    assert _header_texts(panel) == HEADER_SOURCES


def test_panel_controls_use_qt_source_text(panel: RegionDetailPanel) -> None:
    """Core panel controls should use Qt source strings matching existing English YAML."""
    group_label = panel.findChild(QLabel, "optimizeGroupLabel")
    back_button = panel.findChild(QPushButton, "analysisDetailBackButton")
    needs_badge = panel.findChild(QLabel, "optimizeNeedsBadge")
    fit_button = panel.findChild(QPushButton, "analysisDetailFitButton")
    export_button = panel.findChild(QPushButton, "analysisDetailExportButton")
    summary_note_label = panel.findChild(QLabel, "optimizeSummaryNoteLabel")
    add_model_button = panel.findChild(QPushButton, "analysisDetailAddModelButton")

    assert group_label is not None
    assert back_button is not None
    assert needs_badge is not None
    assert fit_button is not None
    assert export_button is not None
    assert summary_note_label is not None
    assert add_model_button is not None

    assert group_label.text() == "Select region"
    assert back_button.text().startswith("←")
    assert back_button.text().endswith("Back to Overview")
    assert back_button.toolTip() == "Return to Analysis Overview (Alt+Left)"
    assert needs_badge.text() == "Needs Optimization"
    assert fit_button.text() == "Run fit"
    assert fit_button.toolTip() == "Load a spectrum to enable fitting."
    assert export_button.text() == "Export Results"
    assert export_button.toolTip() == "Export optimized results as CSV"
    assert summary_note_label.text() == "Load a spectrum to enable fitting."
    assert add_model_button.text() == "Add Component…"


@pytest.mark.parametrize("language", ["en", "ja"])
def test_short_panel_scrolls_without_overlapping_action_buttons(
    qtbot: "QtBot", qapp: QApplication, language: str
) -> None:
    """A short detail panel must preserve every action button's full geometry."""
    with faithful_application_environment(qapp, language):
        panel = _create_panel(qtbot)
        panel.resize(358, 480)

        add_button = panel.findChild(QPushButton, "analysisDetailAddModelButton")
        fit_button = panel.findChild(QPushButton, "analysisDetailFitButton")
        export_button = panel.findChild(QPushButton, "analysisDetailExportButton")
        scroll = panel.findChild(QScrollArea, "analysisDetailSidePanelScroll")
        assert add_button is not None
        assert fit_button is not None
        assert export_button is not None
        assert scroll is not None

        for button in (add_button, fit_button, export_button):
            button.show()
        panel.show()
        qtbot.waitUntil(panel.isVisible, timeout=1000)
        QApplication.processEvents()

        assert scroll.verticalScrollBar().maximum() > 0
        assert add_button.parentWidget() is fit_button.parentWidget()
        assert fit_button.parentWidget() is export_button.parentWidget()
        assert add_button.geometry().bottom() < fit_button.geometry().top()
        assert fit_button.geometry().bottom() < export_button.geometry().top()
        for button in (add_button, fit_button, export_button):
            assert button.height() >= button.minimumSizeHint().height()


def test_qt_translator_updates_existing_header_text(
    panel: RegionDetailPanel, qtbot: "QtBot", qt_translator_installer: QtTranslatorInstaller
) -> None:
    """Existing table headers should update after Qt language changes."""
    _show_panel(panel, qtbot)

    state = qt_translator_installer.install_language("ja")
    assert state.app_translator_loaded
    qtbot.waitUntil(lambda: _header_texts(panel) == HEADER_TRANSLATIONS_JA, timeout=1000)

    qt_translator_installer.install_language("en")
    qtbot.waitUntil(lambda: _header_texts(panel) == HEADER_SOURCES, timeout=1000)


def test_lupdate_extracts_optimize_table_header_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated optimize panel sources without old keys."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[
            Path("src/chappy/gui/modes/analysis/region_detail/panel.py"),
            Path("src/chappy/gui/modes/analysis/region_detail/tree/tree_columns.py"),
            Path(
                "src/chappy/gui/modes/analysis/region_detail/tree/tree_context_menu_controller.py"
            ),
            Path("src/chappy/gui/modes/analysis/region_detail/adapters/confirm_dialog_adapter.py"),
            Path("src/chappy/gui/modes/analysis/region_detail/adapters/export_dialog_adapter.py"),
            Path(
                "src/chappy/gui/modes/analysis/region_detail/workflows/export_workflow_controller.py"
            ),
            Path("src/chappy/gui/modes/analysis/region_detail/mask/mask_panel_adapter.py"),
            Path("src/chappy/gui/modes/analysis/region_detail/views/header_view.py"),
            Path("src/chappy/gui/modes/analysis/region_detail/views/actions_view.py"),
            Path("src/chappy/gui/modes/analysis/region_detail/views/advanced_settings_view.py"),
        ],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert set(HEADER_SOURCES) <= sources
    assert set(PANEL_SOURCES) <= sources
    assert VELOCITY_CONTEXT_MENU_SOURCE in sources
    assert not any("MSG__" in source for source in sources)
    assert not any("DLG__" in source for source in sources)
    assert not any("GUI__" in source for source in sources)
