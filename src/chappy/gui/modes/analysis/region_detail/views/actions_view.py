"""Region Detail actions card: primary buttons and the results summary."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from chappy.gui.common.side_panel_section import SidePanelSection
from chappy.gui.theme import Colors, Fonts, apply_button_variant
from chappy.gui.visual_tokens import SidePanelMetrics
from chappy.presentation.optimize import (
    FitBlockedReason,
    RegionDetailActionState,
    SummaryFitChi2,
    SummaryFitPlaceholder,
    SummaryNoteAddModelComponent,
    SummaryNoteBlocked,
    SummaryNoteCustomMessage,
    SummaryNoteHidden,
    SummaryNoteRunFit,
    SummaryNoteStaleRegion,
    SummaryStateFailed,
    SummaryStateFitted,
    SummaryStateNeedsOptimization,
    SummaryStateNotFitted,
    SummaryStateOptimizing,
    SummaryStatePlaceholder,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.presentation.optimize import (
        SummaryFitDisplay,
        SummaryNoteDisplay,
        SummaryStateDisplay,
    )

_SUMMARY_PLACEHOLDER = "—"


class RegionDetailActionsView(QWidget):
    """Actions card owning the add-model/fit/export buttons and results summary.

    Implements ``RegionActionsViewPort`` directly. State derivation (readiness,
    chi-squared lookups, action-state classification) stays with the panel;
    this view only renders the resulting presentation display objects.
    """

    add_model_clicked = Signal()
    optimize_clicked = Signal()
    export_clicked = Signal()

    def __init__(
        self,
        *,
        request_action_state_refresh: Callable[[], None],
        set_needs_badge_visible: Callable[[bool], None],
        clear_group_summary: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._request_action_state_refresh = request_action_state_refresh
        self._set_needs_badge_visible = set_needs_badge_visible
        self._clear_group_summary = clear_group_summary

        self._frame = SidePanelSection(self, object_name="analysisDetailResultsCard")

        self._add_model_button = QPushButton(self._frame)
        self._add_model_button.setObjectName("analysisDetailAddModelButton")
        self._add_model_button.setVisible(False)
        apply_button_variant(self._add_model_button, "secondary")

        self._optimize_button = QPushButton(self._frame)
        self._optimize_button.setObjectName("analysisDetailFitButton")
        apply_button_variant(self._optimize_button, "primary")
        self._optimize_button.setEnabled(False)

        self._export_button = QPushButton(self._frame)
        self._export_button.setObjectName("analysisDetailExportButton")
        apply_button_variant(self._export_button, "secondary")
        self._export_button.setEnabled(False)

        caption_style = f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SMALL};"
        value_style = f"font-size: {Fonts.SIZE_SMALL};"
        self._summary_title = QLabel(self._frame)
        self._summary_title.setObjectName("optimizeResultsTitle")
        self._summary_title.setStyleSheet(
            f"font-weight: {Fonts.WEIGHT_BOLD}; font-size: {Fonts.SIZE_SMALL};"
        )
        self._summary_state_caption = QLabel(self._frame)
        self._summary_state_caption.setStyleSheet(caption_style)
        self._summary_state_value = QLabel(self._frame)
        self._summary_state_value.setObjectName("optimizeSummaryStateValue")
        self._summary_state_value.setStyleSheet(value_style)
        self._summary_fit_caption = QLabel(self._frame)
        self._summary_fit_caption.setStyleSheet(caption_style)
        self._summary_fit_value = QLabel(self._frame)
        self._summary_fit_value.setObjectName("optimizeSummaryFitValue")
        self._summary_fit_value.setWordWrap(True)
        self._summary_fit_value.setStyleSheet(value_style)
        self._summary_component_caption = QLabel(self._frame)
        self._summary_component_caption.setStyleSheet(caption_style)
        self._summary_component_value = QLabel(self._frame)
        self._summary_component_value.setObjectName("optimizeSummaryComponentValue")
        self._summary_component_value.setStyleSheet(value_style)
        self._summary_note_label = QLabel(self._frame)
        self._summary_note_label.setObjectName("optimizeSummaryNoteLabel")
        self._summary_note_label.setWordWrap(True)
        self._summary_note_label.setStyleSheet(caption_style)

        self._build_layout()

        self._add_model_button.clicked.connect(self.add_model_clicked.emit)
        self._optimize_button.clicked.connect(self.optimize_clicked.emit)
        self._export_button.clicked.connect(self.export_clicked.emit)

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        results_layout = self._frame.body
        results_layout.setSpacing(SidePanelMetrics.SECTION_SPACING // 2)

        # Buttons stack vertically at full width so translated labels survive
        # narrow side-panel widths. The owning panel scrolls vertically when
        # the complete card cannot fit in a short workspace.
        action_column = QVBoxLayout()
        action_column.setContentsMargins(0, 0, 0, 0)
        action_column.setSpacing(SidePanelMetrics.BUTTON_ROW_SPACING)
        for button in (self._add_model_button, self._optimize_button, self._export_button):
            button.setSizePolicy(
                QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            )
            action_column.addWidget(button)
        results_layout.addLayout(action_column)

        results_layout.addWidget(self._summary_title)
        summary_grid = QGridLayout()
        summary_grid.setContentsMargins(0, 0, 0, 0)
        summary_grid.setHorizontalSpacing(SidePanelMetrics.BUTTON_ROW_SPACING)
        summary_grid.setVerticalSpacing(SidePanelMetrics.SECTION_SPACING // 3)
        summary_grid.addWidget(self._summary_state_caption, 0, 0)
        summary_grid.addWidget(self._summary_state_value, 0, 1)
        summary_grid.addWidget(self._summary_fit_caption, 1, 0)
        summary_grid.addWidget(self._summary_fit_value, 1, 1)
        summary_grid.addWidget(self._summary_component_caption, 2, 0)
        summary_grid.addWidget(self._summary_component_value, 2, 1)
        summary_grid.setColumnStretch(1, 1)
        results_layout.addLayout(summary_grid)
        results_layout.addWidget(self._summary_note_label)

    def retranslate_ui(self) -> None:
        """Reapply translated text to all owned widgets."""
        self._optimize_button.setText(self.tr("Run fit"))
        self._export_button.setText(self.tr("Export Results"))
        self._export_button.setToolTip(self.tr("Export optimized results as CSV"))
        self._summary_title.setText(self.tr("Results"))
        self._summary_state_caption.setText(self.tr("Status"))
        self._summary_fit_caption.setText(self.tr("Fit result"))
        self._summary_component_caption.setText(self.tr("Components"))

    def add_model_button(self) -> QPushButton:
        """Return the add-model button (used as the popup-menu anchor)."""
        return self._add_model_button

    def render_action_state(
        self,
        *,
        state: RegionDetailActionState,
        blocked_reason: FitBlockedReason | None,
        add_model_target_label: str | None,
        add_model_visible: bool,
        summary_state_display: SummaryStateDisplay,
        summary_fit_display: SummaryFitDisplay,
        component_count: int | None,
        summary_note_display: SummaryNoteDisplay,
    ) -> None:
        """Render the action buttons and results summary from derived display state."""
        is_empty = state is RegionDetailActionState.EMPTY
        apply_button_variant(self._add_model_button, "primary" if is_empty else "secondary")
        if add_model_target_label is not None:
            self._add_model_button.setText(self.tr("Add Component"))
            #: {name} is a spectral line display name; keep the placeholder.
            self._add_model_button.setToolTip(
                self.tr("Add a model component to {name}").format(name=add_model_target_label)
            )
        else:
            self._add_model_button.setText(self.tr("Add Component…"))
            self._add_model_button.setToolTip(self.tr("Choose the line to add a component to."))
        self._add_model_button.setVisible(add_model_visible)

        self._optimize_button.setVisible(not is_empty)
        self._optimize_button.setEnabled(blocked_reason is None)
        apply_button_variant(
            self._optimize_button,
            "primary" if state is RegionDetailActionState.NEEDS_FIT else "secondary",
        )
        self._optimize_button.setToolTip(
            self.tr("Run fit (F5)")
            if blocked_reason is None
            else self._fit_blocked_text(blocked_reason)
        )

        exportable = state is RegionDetailActionState.FITTED
        self._export_button.setVisible(
            state in (RegionDetailActionState.NEEDS_FIT, RegionDetailActionState.FITTED)
        )
        self._export_button.setEnabled(exportable)
        apply_button_variant(self._export_button, "primary" if exportable else "secondary")

        self._summary_state_value.setText(self._summary_state_text(summary_state_display))
        self._summary_fit_value.setText(self._summary_fit_text(summary_fit_display))
        self._summary_component_value.setText(
            _SUMMARY_PLACEHOLDER if component_count is None else str(component_count)
        )
        note = self._summary_note_text(summary_note_display)
        self._summary_note_label.setText(note)
        self._summary_note_label.setVisible(bool(note))

    def _summary_state_text(self, display: SummaryStateDisplay) -> str:
        if isinstance(display, SummaryStateOptimizing):
            return self.tr("Optimizing…")
        if isinstance(display, SummaryStateFailed):
            return self.tr("Optimization failed")
        if isinstance(display, SummaryStatePlaceholder):
            return _SUMMARY_PLACEHOLDER
        if isinstance(display, SummaryStateFitted):
            return self.tr("Fitted")
        if isinstance(display, SummaryStateNeedsOptimization):
            return self.tr("Needs Optimization")
        if isinstance(display, SummaryStateNotFitted):
            return self.tr("Not fitted")
        typing.assert_never(display)

    def _summary_fit_text(self, display: SummaryFitDisplay) -> str:
        if isinstance(display, SummaryFitPlaceholder):
            return _SUMMARY_PLACEHOLDER
        if isinstance(display, SummaryFitChi2):
            text = self.tr("χ² = {value:.3f}").format(value=display.chi2)
            if display.reduced is not None:
                text = f"{text}  " + self.tr("χ²ν = {value:.3f}").format(value=display.reduced)
            return text
        typing.assert_never(display)

    def _summary_note_text(self, display: SummaryNoteDisplay) -> str:
        if isinstance(display, SummaryNoteHidden):
            return ""
        if isinstance(display, SummaryNoteCustomMessage):
            return display.message
        if isinstance(display, SummaryNoteBlocked):
            return self._fit_blocked_text(display.reason)
        if isinstance(display, SummaryNoteAddModelComponent):
            return self.tr("Add a model component to this region to enable fitting.")
        if isinstance(display, SummaryNoteStaleRegion):
            return self.tr("The region structure changed; run the fit again to refresh results.")
        if isinstance(display, SummaryNoteRunFit):
            return self.tr("Run a fit to see results here.")
        typing.assert_never(display)

    def _fit_blocked_text(self, reason: FitBlockedReason) -> str:
        """Return the one-line reason and next step for a blocked fit."""
        if reason is FitBlockedReason.FIT_RUNNING:
            return self.tr("Optimizing...")
        if reason is FitBlockedReason.NO_SPECTRUM:
            return self.tr("Load a spectrum to enable fitting.")
        if reason is FitBlockedReason.NO_REGION_SELECTED:
            return self.tr("Select a region to enable fitting.")
        return self.tr("Add a model component to this region to enable fitting.")

    # -- RegionActionsViewPort ---------------------------------------------------

    def set_export_controls_state(self, *, export_enabled: bool, needs_visible: bool) -> None:
        """Apply export button and needs badge state."""
        self._export_button.setEnabled(export_enabled)
        self._set_needs_badge_visible(needs_visible)
        self._request_action_state_refresh()

    def update_group_optimize_button_state(self) -> None:
        """Refresh optimize button state after group list changes."""
        self._request_action_state_refresh()

    def clear_group_summary(self) -> None:
        """Clear the group summary label."""
        self._clear_group_summary()
