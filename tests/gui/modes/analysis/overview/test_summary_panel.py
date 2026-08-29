"""Tests for the Analysis Overview summary panel layout and actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QWidget

from chappy.core.analysis import AnalysisReadiness, FitSummary
from chappy.gui.modes.analysis.overview.summary_panel import AnalysisOverviewSummaryPanel
from chappy.presentation.analysis import (
    AnalysisFitResultDisplay,
    AnalysisFitResultKind,
    AnalysisNextAction,
    AnalysisRegionDisplay,
    AnalysisReviewRow,
    AnalysisReviewSummary,
    AnalysisUnavailableCause,
)

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

_STATUS_ITEM_NAMES = (
    "analysisOverviewStatusUnavailable",
    "analysisOverviewStatusNotAnalyzed",
    "analysisOverviewStatusStale",
    "analysisOverviewStatusLatest",
)

_SUMMARY = AnalysisReviewSummary(total=4, unavailable=1, not_analyzed=1, stale=1, latest=1)


def _panel(qtbot: QtBot) -> AnalysisOverviewSummaryPanel:
    panel = AnalysisOverviewSummaryPanel()
    qtbot.addWidget(panel)
    return panel


def _unavailable_row() -> AnalysisReviewRow:
    return AnalysisReviewRow(
        region=AnalysisRegionDisplay("region-1", "Region 1"),
        analysis_status=AnalysisReadiness.UNAVAILABLE,
        fit_result=AnalysisFitResultDisplay(AnalysisFitResultKind.UNAVAILABLE),
        unavailable_causes=(
            AnalysisUnavailableCause.NO_LINES,
            AnalysisUnavailableCause.MISSING_LINE_REFERENCE,
        ),
        next_action=AnalysisNextAction.RESOLVE_PREREQUISITES,
    )


def _latest_row() -> AnalysisReviewRow:
    return AnalysisReviewRow(
        region=AnalysisRegionDisplay("region-1", "Region 1"),
        analysis_status=AnalysisReadiness.LATEST,
        fit_result=AnalysisFitResultDisplay(
            AnalysisFitResultKind.NUMERICAL, FitSummary(reduced_chi_squared=1.0)
        ),
        unavailable_causes=(),
        next_action=AnalysisNextAction.OPEN_REGION,
    )


def test_sections_live_in_scroll_area_with_pinned_buttons(qtbot: QtBot) -> None:
    """All section content stays reachable at 800x600 via a scrollable block."""
    panel = _panel(qtbot)

    scroll = panel.findChild(QScrollArea, "analysisOverviewSummaryScroll")
    assert scroll is not None
    assert scroll.widgetResizable()
    for name in (
        "analysisOverviewStatusCard",
        "analysisOverviewSelection",
        "analysisOverviewReasons",
        "analysisOverviewReadOnlyStructure",
    ):
        widget = panel.findChild(QWidget, name)
        assert widget is not None, name
        assert scroll.isAncestorOf(widget), name

    progress = panel.findChild(QLabel, "analysisOverviewProgress")
    open_button = panel.findChild(QPushButton, "analysisOverviewOpenRegionButton")
    edit_button = panel.findChild(QPushButton, "analysisOverviewEditStructureButton")
    assert progress is not None
    assert open_button is not None
    assert edit_button is not None
    assert not scroll.isAncestorOf(progress)
    assert not scroll.isAncestorOf(open_button)
    assert not scroll.isAncestorOf(edit_button)


def test_panel_does_not_duplicate_right_stack_width_constraints(qtbot: QtBot) -> None:
    """Width limits are centralized on the Analysis right stack (F3)."""
    panel = _panel(qtbot)

    assert panel.minimumWidth() == 0
    assert panel.maximumWidth() > 320


def test_open_region_is_the_primary_action(qtbot: QtBot) -> None:
    """The D5-designated main action carries the primary variant (F10)."""
    panel = _panel(qtbot)

    open_button = panel.findChild(QPushButton, "analysisOverviewOpenRegionButton")
    edit_button = panel.findChild(QPushButton, "analysisOverviewEditStructureButton")
    assert open_button is not None
    assert edit_button is not None
    assert open_button.property("variant") == "primary"
    assert edit_button.property("variant") == "secondary"


def test_render_summary_updates_progress_and_status_grid(qtbot: QtBot) -> None:
    """Aggregate counts render as a progress line plus per-status items."""
    panel = _panel(qtbot)

    panel.render_summary(_SUMMARY)

    progress = panel.findChild(QLabel, "analysisOverviewProgress")
    assert progress is not None
    assert "1" in progress.text()
    assert "4" in progress.text()
    for name in _STATUS_ITEM_NAMES:
        item = panel.findChild(QLabel, name)
        assert item is not None, name
        assert item.text().endswith("1")
        assert item.isEnabled()
        assert item.toolTip()


def test_needs_review_and_export_ready_chips_are_removed(qtbot: QtBot) -> None:
    """The cross-axis chips no longer exist; the four statuses are the only axis."""
    panel = _panel(qtbot)
    panel.render_summary(_SUMMARY)

    assert panel.findChild(QLabel, "analysisOverviewNeedsReviewChip") is None
    assert panel.findChild(QLabel, "analysisOverviewExportReadyChip") is None


def test_zero_count_status_items_are_dimmed_and_unclickable(qtbot: QtBot) -> None:
    """0-count statuses disable to render in the dimmed palette color."""
    panel = _panel(qtbot)
    panel.render_summary(
        AnalysisReviewSummary(total=1, unavailable=0, not_analyzed=0, stale=0, latest=1)
    )

    stale = panel.findChild(QLabel, "analysisOverviewStatusStale")
    latest = panel.findChild(QLabel, "analysisOverviewStatusLatest")
    assert stale is not None and not stale.isEnabled()
    assert latest is not None and latest.isEnabled()

    spy = QSignalSpy(panel.readiness_filter_requested)
    qtbot.mouseClick(stale, Qt.MouseButton.LeftButton)
    assert spy.count() == 0


def test_status_clicks_request_matching_filters(qtbot: QtBot) -> None:
    """Count clicks translate into region-list filter switch requests."""
    panel = _panel(qtbot)
    panel.render_summary(_SUMMARY)
    spy = QSignalSpy(panel.readiness_filter_requested)

    stale = panel.findChild(QLabel, "analysisOverviewStatusStale")
    assert stale is not None
    qtbot.mouseClick(stale, Qt.MouseButton.LeftButton)
    assert spy.count() == 1
    assert spy.at(0)[0] == AnalysisReadiness.STALE.value


def test_empty_state_offers_next_action_and_disabled_reason_tooltips(qtbot: QtBot) -> None:
    """No selection shows guidance, a first-region link, and action tooltips."""
    panel = _panel(qtbot)

    panel.render_selection(None, None)

    select_first = panel.findChild(QPushButton, "analysisOverviewSelectFirstButton")
    open_button = panel.findChild(QPushButton, "analysisOverviewOpenRegionButton")
    edit_button = panel.findChild(QPushButton, "analysisOverviewEditStructureButton")
    assert select_first is not None
    assert not select_first.isHidden()
    assert open_button is not None and not open_button.isEnabled()
    assert edit_button is not None and not edit_button.isEnabled()
    assert open_button.toolTip()
    assert edit_button.toolTip()

    spy = QSignalSpy(panel.first_region_requested)
    select_first.click()
    assert spy.count() == 1

    panel.render_selection(_latest_row(), None)
    assert select_first.isHidden()
    assert open_button.isEnabled()
    assert open_button.toolTip() == ""


def test_unavailable_causes_render_one_item_per_line_with_tooltips(qtbot: QtBot) -> None:
    """Causes list one label per cause, each carrying a resolution tooltip."""
    panel = _panel(qtbot)

    panel.render_selection(_unavailable_row(), None)

    reasons = panel.findChild(QWidget, "analysisOverviewReasons")
    assert reasons is not None
    assert not reasons.isHidden()
    items = reasons.findChildren(QLabel, "analysisOverviewReasonItem")
    assert len(items) == 2
    assert all(item.toolTip() for item in items)

    panel.render_selection(_latest_row(), None)
    assert reasons.isHidden()
    live_items = [
        item
        for item in reasons.findChildren(QLabel, "analysisOverviewReasonItem")
        if not item.isHidden()
    ]
    assert live_items == []
