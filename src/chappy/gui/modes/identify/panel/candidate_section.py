"""Sigma threshold and detection candidate section for the identify side panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from collections.abc import Sequence

    from PySide6.QtGui import QKeyEvent, QMouseEvent

    from chappy.gui.modes.identify.panel.panel_models import CandidateRow

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.common.side_panel_heading import apply_side_panel_heading_style
from chappy.gui.modes.identify.panel.panel_models import CandidateTableItemPayload
from chappy.gui.modes.identify.panel.table_items import SortableNumericItem
from chappy.gui.theme import Colors, empty_state_label_style
from chappy.gui.visual_tokens import LayoutMetrics, SidePanelMetrics

_SIGMA_COLUMN_TEMPLATE = "9999.9"
_SIGMA_CELL_HORIZONTAL_PADDING = 8
_STATUS_COLUMN_WIDTH = 100


class _CandidateTableWidget(QTableWidget):
    """Table whose Qt activation signal consistently covers Enter and double-click."""

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Activate the current row when Enter or Return is pressed."""
        if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return) and self.currentRow() >= 0:
            self.cellActivated.emit(self.currentRow(), max(0, self.currentColumn()))
            event.accept()
            return
        super().keyPressEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Convert a double-click into exactly one Qt activation signal."""
        item = self.itemAt(event.position().toPoint())
        if item is None:
            super().mouseDoubleClickEvent(event)
            return
        was_blocked = self.blockSignals(True)
        super().mouseDoubleClickEvent(event)
        self.blockSignals(was_blocked)
        self.cellActivated.emit(item.row(), item.column())


class IdentifyCandidateSection(QWidget):
    """Detection candidate table with the fused sigma-threshold controls."""

    sigma_threshold_changed = Signal(float)
    candidate_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Construct the candidate section."""
        super().__init__(parent)
        self.setObjectName("identifyCandidateSection")
        self._candidate_count = 0

        self._sigma_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._sigma_slider.setRange(20, 1000)
        self._sigma_slider.setSingleStep(1)
        self._sigma_slider.setPageStep(5)
        self._sigma_slider.setTickInterval(5)
        self._sigma_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self._sigma_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._sigma_spin = QDoubleSpinBox(self)
        self._sigma_spin.setDecimals(1)
        self._sigma_spin.setRange(2.0, 100.0)
        self._sigma_spin.setSingleStep(0.1)
        self._sigma_spin.setKeyboardTracking(False)
        self._sigma_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._sigma_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._sigma_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._sigma_spin.setFixedWidth(LayoutMetrics.NUMERIC_INPUT_WIDTH)

        self._sigma_label = QLabel(self)
        self._sigma_label.setObjectName("identifySigmaThresholdLabel")
        self._sigma_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self._candidate_table = _CandidateTableWidget(self)
        self._candidate_table.setObjectName("identifyCandidateTable")
        self._candidate_table.setColumnCount(3)
        self._candidate_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._candidate_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._candidate_table.setAlternatingRowColors(True)
        self._candidate_table.verticalHeader().setVisible(False)
        candidate_header = self._candidate_table.horizontalHeader()
        candidate_header.setStretchLastSection(False)
        candidate_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        candidate_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        candidate_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        sigma_column_width = (
            self._candidate_table.fontMetrics().horizontalAdvance(_SIGMA_COLUMN_TEMPLATE)
            + _SIGMA_CELL_HORIZONTAL_PADDING
        )
        self._candidate_table.setColumnWidth(1, sigma_column_width)
        self._candidate_table.setColumnWidth(2, _STATUS_COLUMN_WIDTH)
        candidate_header.setSectionsClickable(True)
        candidate_header.setSortIndicatorShown(True)
        self._candidate_table.setSortingEnabled(True)

        self._candidate_placeholder = QLabel(self)
        self._candidate_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._candidate_placeholder.setWordWrap(True)
        self._candidate_placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._candidate_placeholder.setStyleSheet(empty_state_label_style())

        self._build_layout()
        self._connect_signals()
        self.retranslate_ui()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SidePanelMetrics.SECTION_SPACING)

        self._candidate_section_label = QLabel(self)
        self._candidate_section_label.setObjectName("identifyCandidateSectionLabel")
        apply_side_panel_heading_style(self._candidate_section_label)
        root.addWidget(self._candidate_section_label)

        sigma_row = QHBoxLayout()
        sigma_row.setContentsMargins(0, 0, 0, 0)
        sigma_row.setSpacing(SidePanelMetrics.BUTTON_ROW_SPACING)
        sigma_row.addWidget(self._sigma_label)
        sigma_row.addWidget(self._sigma_slider, 1)
        sigma_row.addWidget(self._sigma_spin)
        root.addLayout(sigma_row)

        self._candidate_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self._candidate_stack = QStackedWidget(self)
        self._candidate_stack.setObjectName("identifyCandidateStack")
        self._candidate_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._candidate_stack.addWidget(self._candidate_table)

        placeholder_page = QWidget(self)
        placeholder_layout = QVBoxLayout(placeholder_page)
        placeholder_layout.setContentsMargins(
            SidePanelMetrics.PLACEHOLDER_PADDING,
            SidePanelMetrics.PLACEHOLDER_PADDING,
            SidePanelMetrics.PLACEHOLDER_PADDING,
            SidePanelMetrics.PLACEHOLDER_PADDING,
        )
        placeholder_layout.setSpacing(0)
        placeholder_layout.addWidget(self._candidate_placeholder, 0, Qt.AlignmentFlag.AlignTop)
        placeholder_layout.addStretch()
        self._candidate_placeholder_page: QWidget = placeholder_page
        self._candidate_stack.addWidget(placeholder_page)
        self._candidate_stack.setCurrentWidget(placeholder_page)

        root.addWidget(self._candidate_stack, 1)

        self._hint_label = QLabel(self)
        self._hint_label.setObjectName("identifyCandidateHint")
        self._hint_label.setWordWrap(True)
        self._hint_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")

        root.addWidget(self._hint_label)

    def _connect_signals(self) -> None:
        self._sigma_slider.valueChanged.connect(self._on_sigma_slider_changed)
        self._sigma_spin.valueChanged.connect(self._on_sigma_spin_changed)
        self._candidate_table.cellActivated.connect(self._activate_candidate_row)

    def retranslate_ui(self) -> None:
        """Apply the active language to all visible strings."""
        self._update_section_heading()
        self._candidate_placeholder.setText(
            self.tr("No detection candidates. Lower the σ threshold to find more.")
        )
        self._sigma_label.setText(self.tr("σ threshold"))
        self._sigma_spin.setSuffix(self.tr(" σ"))
        self._hint_label.setText(
            self.tr(
                "Double-click a candidate to move there. "
                "Then hold Shift to preview, Shift+click to add, or press V to verify"
            )
        )
        self._candidate_table.setHorizontalHeaderLabels(
            [self.tr("λ range [Å]"), self.tr("σ"), self.tr("Status")]
        )

    def set_candidates(self, candidates: Sequence[CandidateRow]) -> None:
        """Populate the detection candidate table."""
        header = self._candidate_table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        sorting_enabled = self._candidate_table.isSortingEnabled()

        self._candidate_table.blockSignals(True)
        self._candidate_table.setSortingEnabled(False)
        self._candidate_table.setRowCount(0)
        self._candidate_table.clearContents()

        self._candidate_table.setRowCount(len(candidates))
        for row, candidate in enumerate(candidates):
            range_text = f"{candidate.lambda_start:.1f}–{candidate.lambda_end:.1f}"
            range_item = SortableNumericItem(range_text, candidate.lambda_start)
            range_item.setToolTip(f"{candidate.lambda_start:.3f}–{candidate.lambda_end:.3f} Å")
            range_item.setData(
                Qt.ItemDataRole.UserRole,
                CandidateTableItemPayload(
                    candidate_id=candidate.identifier, lambda_start=candidate.lambda_start
                ),
            )

            sigma_item = SortableNumericItem(f"{candidate.sigma:.1f}", candidate.sigma)
            sigma_item.setData(Qt.ItemDataRole.UserRole, candidate.sigma)
            status_item = QTableWidgetItem(self._status_badge_text(candidate.status))
            status_item.setData(Qt.ItemDataRole.UserRole, candidate.status)
            status_item.setToolTip(self._status_tooltip(candidate.status))

            for item in (range_item, sigma_item, status_item):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

            sigma_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._candidate_table.setItem(row, 0, range_item)
            self._candidate_table.setItem(row, 1, sigma_item)
            self._candidate_table.setItem(row, 2, status_item)

        self._candidate_count = len(candidates)
        self._update_section_heading()
        if candidates:
            self._candidate_stack.setCurrentWidget(self._candidate_table)
        else:
            self._candidate_stack.setCurrentWidget(self._candidate_placeholder_page)
        self._candidate_table.setSortingEnabled(sorting_enabled)
        if sorting_enabled and sort_column >= 0:
            self._candidate_table.sortItems(sort_column, sort_order)
        self._candidate_table.blockSignals(False)

    def set_sigma_threshold(self, value: float) -> None:
        """Synchronize the sigma slider with the provided value."""
        slider_value = round(value * 10)
        self._sigma_slider.blockSignals(True)
        self._sigma_slider.setValue(slider_value)
        self._sigma_slider.blockSignals(False)
        self._sigma_spin.blockSignals(True)
        self._sigma_spin.setValue(round(value, 1))
        self._sigma_spin.blockSignals(False)

    @property
    def current_sigma_value(self) -> float:
        """Return the slider value converted back to σ units."""
        return self._sigma_slider.value() / 10.0

    def _update_section_heading(self) -> None:
        #: {count} is the number of detection candidates.
        template = self.tr("Detection Candidates ({count})")
        self._candidate_section_label.setText(template.format(count=self._candidate_count))

    def _on_sigma_slider_changed(self, _: int) -> None:
        value = self.current_sigma_value
        self._sigma_spin.blockSignals(True)
        self._sigma_spin.setValue(round(value, 1))
        self._sigma_spin.blockSignals(False)
        self.sigma_threshold_changed.emit(value)

    def _on_sigma_spin_changed(self, value: float) -> None:
        slider_value = round(value * 10)
        self._sigma_slider.blockSignals(True)
        self._sigma_slider.setValue(slider_value)
        self._sigma_slider.blockSignals(False)
        self.sigma_threshold_changed.emit(value)

    def _activate_candidate_row(self, row: int, _column: int) -> None:
        """Emit the candidate represented by an activated visual row."""
        item = self._candidate_table.item(row, 0)
        if item is None:
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, CandidateTableItemPayload):
            self.candidate_activated.emit(payload.candidate_id)

    def _status_badge_text(self, status: str) -> str:
        mapping = {
            "identified": self.tr("Registered"),
            "candidate": self.tr("Tentative"),
            "unused": self.tr("Unassigned"),
        }
        return mapping.get(status, status.title())

    def _status_tooltip(self, status: str) -> str:
        mapping = {
            "identified": self.tr("Matched to a line in a confirmed region."),
            "candidate": self.tr("A temporary line is placed. Not final until registered."),
            "unused": self.tr("A dip not yet matched to any line."),
        }
        return mapping.get(status, "")

    @override
    def changeEvent(self, event: QEvent) -> None:
        """Refresh translated text when Qt installs a new translator."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
