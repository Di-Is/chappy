"""Preset and reference-line setup header for the identify side panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chappy.gui.modes.identify.panel.panel_models import LineListItem

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QComboBox, QGridLayout, QLabel, QPushButton, QSizePolicy, QWidget

from chappy.core.velocity_ranges import (
    MAX_ANALYSIS_HALF_WIDTH_KMS,
    MIN_ANALYSIS_HALF_WIDTH_KMS,
    NewCandidateAnalysisHalfWidth,
)
from chappy.gui.modes.identify.panel.new_candidate_half_width_spinbox import (
    NewCandidateAnalysisHalfWidthSpinBox,
    NewCandidateHalfWidthRejection,
)
from chappy.gui.theme import Colors, apply_button_variant
from chappy.gui.visual_tokens import SidePanelMetrics


class IdentifyPresetLinesSection(QWidget):
    """Two-row setup header with preset and reference-line selectors."""

    preset_changed = Signal(str)
    manage_presets_requested = Signal()
    reference_line_changed = Signal(str)
    new_candidate_analysis_half_width_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Construct the preset setup header."""
        super().__init__(parent)
        self.setObjectName("identifyPresetLinesSection")

        self._preset_combo = QComboBox(self)
        self._preset_combo.setObjectName("identifyPresetCombo")
        self._manage_preset_button = QPushButton(self)
        self._manage_preset_button.setObjectName("identifyManagePresetButton")
        self._manage_preset_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        apply_button_variant(self._manage_preset_button, "secondary")

        self._reference_combo = QComboBox(self)
        self._reference_combo.setObjectName("identifyReferenceLineCombo")
        self._reference_model = QStandardItemModel(self._reference_combo)
        self._reference_combo.setModel(self._reference_model)
        self._reference_combo.setMaxVisibleItems(50)
        self._reference_combo.setEnabled(False)
        self._line_multiplet_map: dict[str, str] = {}
        self._current_reference_line_id: str | None = None
        self._last_half_width_rejection: NewCandidateHalfWidthRejection | None = None

        self._build_layout()
        self._connect_signals()
        self.retranslate_ui()

    def _build_layout(self) -> None:
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(SidePanelMetrics.BUTTON_ROW_SPACING)
        grid.setVerticalSpacing(SidePanelMetrics.ACTION_CARD_COMPACT_SPACING)

        self._preset_label = QLabel(self)
        self._preset_label.setObjectName("identifyPresetLabel")
        self._preset_label.setBuddy(self._preset_combo)
        self._configure_combo_sizing(self._preset_combo)

        self._reference_label = QLabel(self)
        self._reference_label.setObjectName("identifyReferenceLineLabel")
        self._reference_label.setBuddy(self._reference_combo)
        self._configure_combo_sizing(self._reference_combo)

        self._half_width_label = QLabel(self)
        self._half_width_label.setObjectName("identifyNewCandidateAnalysisHalfWidthLabel")
        self._half_width_spinbox = NewCandidateAnalysisHalfWidthSpinBox(self)
        self._half_width_label.setBuddy(self._half_width_spinbox)

        grid.addWidget(self._preset_label, 0, 0)
        grid.addWidget(self._preset_combo, 0, 1)
        grid.addWidget(self._manage_preset_button, 0, 2, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self._reference_label, 1, 0)
        grid.addWidget(self._reference_combo, 1, 1, 1, 2)
        grid.addWidget(self._half_width_label, 2, 0, 1, 2)
        grid.addWidget(self._half_width_spinbox, 2, 2, Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(1, 1)

        self._half_width_error_label = QLabel(self)
        self._half_width_error_label.setObjectName("identifyNewCandidateHalfWidthError")
        self._half_width_error_label.setWordWrap(True)
        self._half_width_error_label.setStyleSheet(f"color: {Colors.WARNING};")
        self._half_width_error_label.setVisible(False)
        grid.addWidget(self._half_width_error_label, 3, 0, 1, 3)

    @staticmethod
    def _configure_combo_sizing(combo: QComboBox) -> None:
        """Guarantee a readable closed width instead of collapsing with the panel."""
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumContentsLength(8)
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

    def _connect_signals(self) -> None:
        self._preset_combo.currentIndexChanged.connect(self._emit_preset_selection)
        self._manage_preset_button.clicked.connect(self.manage_presets_requested)
        self._reference_combo.currentIndexChanged.connect(self._emit_reference_selection)
        self._half_width_spinbox.value_accepted.connect(self._on_half_width_accepted)
        self._half_width_spinbox.input_rejected.connect(self._on_half_width_rejected)

    def retranslate_ui(self) -> None:
        """Apply the active language to all visible strings."""
        self._preset_label.setText(self.tr("Preset"))
        self._manage_preset_button.setText(self.tr("Manage⚙"))
        self._reference_label.setText(self.tr("Reference line"))
        self._reference_combo.setAccessibleName(self.tr("Reference line"))
        self._half_width_label.setText(self.tr("New-candidate range"))
        self._apply_half_width_accessibility()
        self._render_half_width_rejection()
        self._sync_preset_control_metrics()

    def set_presets(self, presets: Sequence[tuple[str, str]], current: str | None = None) -> None:
        """Populate the preset combo and optionally select the current entry."""
        block = self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        for preset_id, label in presets:
            self._preset_combo.addItem(label, preset_id)

        index = -1
        if current is not None:
            index = self._preset_combo.findData(current)
        if index < 0 and self._preset_combo.count() > 0:
            index = 0
        if index >= 0:
            self._preset_combo.setCurrentIndex(index)
        self._preset_combo.blockSignals(block)

    def set_line_items(self, items: Sequence[LineListItem]) -> None:
        """Rebuild the reference-line combo without emitting a selection change."""
        block = self._reference_combo.blockSignals(True)
        self._reference_model.clear()
        self._line_multiplet_map = {}
        self._current_reference_line_id = None

        for item in sorted(items, key=lambda entry: entry.wavelength):
            display_name = item.name or item.reference
            model_item = QStandardItem(f"{display_name} {item.wavelength:.3f}")
            model_item.setData(item.identifier, Qt.ItemDataRole.UserRole)
            model_item.setToolTip(
                f"f = {item.oscillator_strength:.3f}, λ = {item.wavelength:.3f} Å"
            )
            self._reference_model.appendRow(model_item)
            self._line_multiplet_map[item.identifier] = item.multiplet_id
            if item.is_reference:
                self._current_reference_line_id = item.identifier

        if self._current_reference_line_id is None and items:
            self._current_reference_line_id = items[0].identifier

        reference_index = self._reference_index_of(self._current_reference_line_id)
        if reference_index >= 0:
            self._reference_combo.setCurrentIndex(reference_index)
        self._reference_combo.setEnabled(self._reference_model.rowCount() > 0)
        self._reference_combo.blockSignals(block)
        self._apply_multiplet_highlight()
        self._sync_reference_tooltip()

    def set_new_candidate_analysis_half_width(self, value: NewCandidateAnalysisHalfWidth) -> None:
        """Render the current future-candidate draft without emitting user intent."""
        self._half_width_spinbox.set_accepted_value(value)
        self._last_half_width_rejection = None
        self._render_half_width_rejection()

    def _on_half_width_accepted(self, value: object) -> None:
        if not isinstance(value, NewCandidateAnalysisHalfWidth):
            msg = "New-candidate half-width signal requires the validated value type."
            raise TypeError(msg)
        self._last_half_width_rejection = None
        self._render_half_width_rejection()
        self.new_candidate_analysis_half_width_changed.emit(value)

    def _on_half_width_rejected(self, rejection: object) -> None:
        if not isinstance(rejection, NewCandidateHalfWidthRejection):
            msg = "New-candidate half-width rejection has an invalid payload."
            raise TypeError(msg)
        self._last_half_width_rejection = rejection
        self._render_half_width_rejection()

    def _render_half_width_rejection(self) -> None:
        rejection = self._last_half_width_rejection
        if rejection is None:
            self._half_width_error_label.clear()
            self._half_width_error_label.setVisible(False)
            self._apply_half_width_accessibility()
            return
        if rejection.reason == "invalid_number":
            message = self.tr("Enter a valid numeric range.")
        else:
            #: {minimum} and {maximum} are supported half-widths in km/s.
            template = self.tr(
                "New-candidate range must be between ±{minimum:g} and ±{maximum:g} km/s."
            )
            message = template.format(
                minimum=MIN_ANALYSIS_HALF_WIDTH_KMS, maximum=MAX_ANALYSIS_HALF_WIDTH_KMS
            )
        self._half_width_error_label.setText(message)
        self._half_width_error_label.setAccessibleDescription(message)
        self._half_width_error_label.setVisible(True)
        self._half_width_spinbox.setAccessibleDescription(message)

    def _apply_half_width_accessibility(self) -> None:
        self._half_width_spinbox.setAccessibleName(self.tr("New-candidate analysis range"))
        self._half_width_spinbox.setAccessibleDescription(
            self.tr(
                "Symmetric analysis range in ±km/s for Shift previews and newly added "
                "candidates. Existing temporary lines, velocity display range, and grouping "
                "results are unchanged."
            )
        )

    def _sync_preset_control_metrics(self) -> None:
        """Align preset combo and manage button dimensions for visual balance."""
        combo_height = self._preset_combo.sizeHint().height()
        if combo_height <= 0:
            return

        self._preset_combo.setMinimumHeight(combo_height)
        self._manage_preset_button.setMinimumHeight(combo_height)
        self._manage_preset_button.setMaximumHeight(combo_height)

        icon_side = max(16, combo_height - 8)
        self._manage_preset_button.setIconSize(QSize(icon_side, icon_side))

    def _emit_preset_selection(self, index: int) -> None:
        preset_id = self._preset_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if isinstance(preset_id, str):
            self.preset_changed.emit(preset_id)

    def _emit_reference_selection(self, index: int) -> None:
        if index < 0:
            return
        line_id = self._reference_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if isinstance(line_id, str):
            self._current_reference_line_id = line_id
            self._apply_multiplet_highlight()
            self._sync_reference_tooltip()
            self.reference_line_changed.emit(line_id)

    def _reference_index_of(self, line_id: str | None) -> int:
        if line_id is None:
            return -1
        return self._reference_combo.findData(line_id, Qt.ItemDataRole.UserRole)

    def _sync_reference_tooltip(self) -> None:
        index = self._reference_combo.currentIndex()
        item = self._reference_model.item(index) if index >= 0 else None
        self._reference_combo.setToolTip(item.toolTip() if item is not None else "")

    def _apply_multiplet_highlight(self) -> None:
        reference_id = self._current_reference_line_id
        reference_multiplet = self._line_multiplet_map.get(reference_id or "", "")
        highlight_color = QColor(Colors.ACCENT_SELECTION_LIGHT)
        highlight_color.setAlpha(100)

        for row in range(self._reference_model.rowCount()):
            item = self._reference_model.item(row)
            line_id = item.data(Qt.ItemDataRole.UserRole)
            multiplet_id = (
                self._line_multiplet_map.get(line_id, "") if isinstance(line_id, str) else ""
            )
            highlight = (line_id == reference_id) or (
                bool(reference_multiplet) and multiplet_id == reference_multiplet
            )
            item.setData(highlight_color if highlight else None, Qt.ItemDataRole.BackgroundRole)

    @override
    def changeEvent(self, event: QEvent) -> None:
        """Refresh translated text when Qt installs a new translator."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
