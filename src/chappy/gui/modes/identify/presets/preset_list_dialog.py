"""Identify preset list dialog implementing SCR-DIA-PSL requirements."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QItemSelectionModel, QSize, Qt, QTimer, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chappy.application.presets import (
    PresetTieGroupSuggestion,
    suggest_preset_tie_groups,
    validate_preset_tie_group_members,
)
from chappy.core.presets import (
    LineIdentifier,
    Preset,
    PresetExportError,
    PresetImportError,
    PresetImportSummary,
    TieGroupIssue,
)
from chappy.gui.dialog_sizing import enforce_translated_minimum_size
from chappy.gui.dialogs.line_selection_dialog import LineSelectionDialog
from chappy.gui.theme import (
    Colors,
    apply_action_row_sizing,
    apply_button_variant,
    card_frame_style,
)
from chappy.gui.visual_tokens import DialogMetrics
from chappy.i18n import get_language_switcher

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from chappy.core.atomic_data import AtomicLine, AtomicLineData
    from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore

logger = logging.getLogger(__name__)

MISSING_LINE_PREVIEW_LIMIT = 5


def _optional_string_item_data(value: object, *, field_name: str) -> str | None:
    """Return string item data or fail on an unexpected Qt payload."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    msg = f"{field_name} item data must be a string or None."
    raise TypeError(msg)


@dataclass
class _LineDisplay:
    """Display payload bound to table widget items."""

    identifier: LineIdentifier
    label: str
    wavelength: float
    oscillator_strength: float
    atomic_line: AtomicLine | None
    tie_group_uid: str | None


class PresetListDialog(QDialog):
    """Modal dialog for browsing and editing absorption presets."""

    def __init__(
        self,
        parent: QWidget | None,
        preset_store: IdentifyPresetStore,
        *,
        atomic_data: AtomicLineData,
    ) -> None:
        """Build dialog widgets and load initial preset state."""
        super().__init__(parent)

        self.setModal(True)
        self.setSizeGripEnabled(True)
        self.setObjectName("presetListDialog")

        self._preset_store = preset_store
        self._atomic_data = atomic_data
        self._language_switcher = get_language_switcher(self)
        self._preset_cache: dict[str, Preset] = {}
        self._current_preset_id: str | None = None
        self._updating_baseline = False
        self._list_heading_label: QLabel | None = None
        self._baseline_field_label: QLabel | None = None
        self._current_suggestions: tuple[PresetTieGroupSuggestion, ...] = ()

        self._build_ui()
        self._connect_store_signals()
        self._refresh_presets()
        self._select_initial_preset()
        self._apply_translations()
        self._language_switcher.language_changed.connect(self._on_language_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        left_panel = self._build_preset_list_panel()
        content_row.addWidget(left_panel, stretch=1)

        right_panel = self._build_detail_panel()
        content_row.addWidget(right_panel, stretch=2)

        layout.addLayout(content_row, 1)

        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        self._button_box.setObjectName("presetButtonBox")
        close_btn = self._button_box.button(QDialogButtonBox.StandardButton.Close)
        if isinstance(close_btn, QPushButton):
            close_btn.setObjectName("presetCloseButton")
            apply_button_variant(close_btn, "secondary")
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

    def _build_preset_list_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        list_card = QFrame(panel)
        list_card.setObjectName("presetListFrame")
        list_card.setStyleSheet(card_frame_style("presetListFrame"))
        list_card.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        list_card_layout = QVBoxLayout(list_card)
        list_card_layout.setContentsMargins(12, 12, 12, 12)
        list_card_layout.setSpacing(8)

        self._list_heading_label = QLabel(list_card)
        self._list_heading_label.setStyleSheet("font-weight: 600;")
        list_card_layout.addWidget(self._list_heading_label)

        self._preset_list = QListWidget(list_card)
        self._preset_list.setObjectName("presetListView")
        self._preset_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._preset_list.itemSelectionChanged.connect(self._on_preset_selection_changed)
        self._preset_list.setAlternatingRowColors(True)
        self._preset_list.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        list_card_layout.addWidget(self._preset_list, stretch=1)

        layout.addWidget(list_card, stretch=1)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self._new_button = QPushButton(panel)
        self._new_button.setObjectName("presetNewButton")
        self._new_button.clicked.connect(self._on_new_preset)
        apply_button_variant(self._new_button, "primary")

        self._duplicate_button = QPushButton(panel)
        self._duplicate_button.setObjectName("presetDuplicateButton")
        self._duplicate_button.clicked.connect(self._on_duplicate_preset)
        self._duplicate_button.setEnabled(False)
        apply_button_variant(self._duplicate_button, "secondary")

        self._rename_button = QPushButton(panel)
        self._rename_button.setObjectName("presetRenameButton")
        self._rename_button.clicked.connect(self._on_rename_preset)
        self._rename_button.setEnabled(False)
        apply_button_variant(self._rename_button, "secondary")

        self._delete_button = QPushButton(panel)
        self._delete_button.setObjectName("presetDeleteButton")
        self._delete_button.clicked.connect(self._on_delete_preset)
        self._delete_button.setEnabled(False)
        apply_button_variant(self._delete_button, "danger")

        apply_action_row_sizing(
            self._new_button, self._duplicate_button, self._rename_button, self._delete_button
        )
        for button in (
            self._new_button,
            self._duplicate_button,
            self._rename_button,
            self._delete_button,
        ):
            button.setSizePolicy(
                QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            )
            actions_row.addWidget(button)

        layout.addLayout(actions_row)

        sharing_row = QHBoxLayout()
        sharing_row.setSpacing(8)

        self._import_button = QPushButton(panel)
        self._import_button.setObjectName("presetImportButton")
        self._import_button.clicked.connect(self._on_import)
        apply_button_variant(self._import_button, "secondary")
        sharing_row.addWidget(self._import_button)

        self._export_button = QPushButton(panel)
        self._export_button.setObjectName("presetExportButton")
        self._export_button.clicked.connect(self._on_export)
        self._export_button.setEnabled(False)
        apply_button_variant(self._export_button, "secondary")
        sharing_row.addWidget(self._export_button)

        apply_action_row_sizing(self._import_button, self._export_button)
        sharing_row.addStretch(1)
        layout.addLayout(sharing_row)

        return panel

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self._selected_label = QLabel(panel)
        self._selected_label.setStyleSheet("font-weight: 600;")
        header_row.addWidget(self._selected_label)

        header_row.addStretch(1)

        self._line_count_label = QLabel(panel)
        self._line_count_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        header_row.addWidget(self._line_count_label)

        layout.addLayout(header_row)

        baseline_row = QHBoxLayout()
        baseline_row.setContentsMargins(0, 0, 0, 0)
        baseline_row.setSpacing(8)

        self._baseline_field_label = QLabel(panel)
        baseline_row.addWidget(self._baseline_field_label)

        self._baseline_combo = QComboBox(panel)
        self._baseline_combo.setObjectName("presetBaselineCombo")
        self._baseline_combo.currentIndexChanged.connect(self._on_baseline_changed)
        self._baseline_combo.setEnabled(False)
        self._baseline_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        baseline_row.addWidget(self._baseline_combo, 1)

        layout.addLayout(baseline_row)

        line_card = QFrame(panel)
        line_card.setObjectName("presetLineFrame")
        line_card.setStyleSheet(card_frame_style("presetLineFrame"))
        line_card.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        card_layout = QVBoxLayout(line_card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)

        self._line_table = QTableWidget(line_card)
        self._line_table.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        )
        self._line_table.setColumnCount(4)
        self._line_table.setAlternatingRowColors(True)
        self._line_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._line_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._line_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._line_table.verticalHeader().setVisible(False)
        self._line_table.setObjectName("presetLineTable")
        header = self._line_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(56)
        selection_model = self._line_table.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(self._update_action_states)
        card_layout.addWidget(self._line_table, stretch=1)

        layout.addWidget(line_card, stretch=1)

        self._suggestion_bar = QFrame(panel)
        self._suggestion_bar.setObjectName("presetSuggestionBar")
        self._suggestion_bar.setStyleSheet(card_frame_style("presetSuggestionBar"))
        suggestion_layout = QHBoxLayout(self._suggestion_bar)
        suggestion_layout.setContentsMargins(12, 8, 12, 8)
        suggestion_layout.setSpacing(8)

        self._suggestion_label = QLabel(self._suggestion_bar)
        self._suggestion_label.setWordWrap(True)
        suggestion_layout.addWidget(self._suggestion_label, 1)

        self._apply_suggestions_button = QPushButton(self._suggestion_bar)
        self._apply_suggestions_button.setObjectName("presetApplySuggestionsButton")
        self._apply_suggestions_button.clicked.connect(self._on_apply_all_suggestions)
        apply_button_variant(self._apply_suggestions_button, "secondary")
        apply_action_row_sizing(self._apply_suggestions_button)
        suggestion_layout.addWidget(self._apply_suggestions_button)

        self._suggestion_bar.setVisible(False)
        layout.addWidget(self._suggestion_bar)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)

        self._add_line_button = QPushButton(panel)
        self._add_line_button.setObjectName("presetAddLineButton")
        self._add_line_button.clicked.connect(self._on_add_line)
        self._add_line_button.setEnabled(False)
        apply_button_variant(self._add_line_button, "secondary")
        buttons_row.addWidget(self._add_line_button)

        self._remove_line_button = QPushButton(panel)
        self._remove_line_button.setObjectName("presetRemoveLineButton")
        self._remove_line_button.clicked.connect(self._on_remove_lines)
        self._remove_line_button.setEnabled(False)
        apply_button_variant(self._remove_line_button, "danger")
        buttons_row.addWidget(self._remove_line_button)

        buttons_row.addStretch(1)

        self._link_button = QPushButton(panel)
        self._link_button.setObjectName("presetAddTieGroupButton")
        self._link_button.clicked.connect(self._on_link_selected_lines)
        self._link_button.setEnabled(False)
        apply_button_variant(self._link_button, "secondary")
        buttons_row.addWidget(self._link_button)

        self._unlink_button = QPushButton(panel)
        self._unlink_button.setObjectName("presetRemoveTieGroupButton")
        self._unlink_button.clicked.connect(self._on_unlink_selected)
        self._unlink_button.setEnabled(False)
        apply_button_variant(self._unlink_button, "secondary")
        buttons_row.addWidget(self._unlink_button)

        apply_action_row_sizing(
            self._add_line_button, self._remove_line_button, self._link_button, self._unlink_button
        )
        layout.addLayout(buttons_row)

        return panel

    def _apply_translations(self) -> None:
        title = self.tr("Absorption Preset Management")
        self.setWindowTitle(title)
        self.setAccessibleName(title)

        if self._button_box is not None:
            close_button = self._button_box.button(QDialogButtonBox.StandardButton.Close)

            close_text = self.tr("Close")

            if close_button is not None:
                close_button.setText(close_text)
                close_button.setAccessibleName(close_text)

        if self._list_heading_label is not None:
            text = self.tr("Presets")
            self._list_heading_label.setText(text)

        self._new_button.setText(self.tr("New"))
        self._duplicate_button.setText(self.tr("Duplicate"))
        self._rename_button.setText(self.tr("Rename"))
        self._delete_button.setText(self.tr("Delete"))
        self._import_button.setText(self.tr("Import..."))
        self._export_button.setText(self.tr("Export..."))
        self._add_line_button.setText(self.tr("Add Line"))
        self._remove_line_button.setText(self.tr("Remove Selected"))
        self._link_button.setText(self.tr("Link selected lines"))
        self._unlink_button.setText(self.tr("Unlink"))
        self._apply_suggestions_button.setText(self.tr("Apply all"))

        if self._baseline_field_label is not None:
            baseline_label = self.tr("Reference line:")
            self._baseline_field_label.setText(baseline_label)

        self._refresh_system_preset_tooltips()
        self._update_line_headers()
        self._populate_detail(self._current_preset())
        self._update_action_states()
        enforce_translated_minimum_size(
            self,
            floor=QSize(*DialogMetrics.MIN_SIZE_PRESET_LIST),
            initial=QSize(*DialogMetrics.INITIAL_SIZE_PRESET_LIST),
        )

    def _refresh_system_preset_tooltips(self) -> None:
        """Reapply the read-only tooltip for system presets in the active language."""
        tooltip = self.tr("System preset (read-only)")
        for index in range(self._preset_list.count()):
            item = self._preset_list.item(index)
            if item is None:
                continue
            preset_id = _optional_string_item_data(
                item.data(Qt.ItemDataRole.UserRole), field_name="Preset id"
            )
            preset = self._preset_cache.get(preset_id) if preset_id else None
            if preset is not None and not preset.is_editable:
                item.setToolTip(tooltip)

    def _update_line_headers(self) -> None:
        headers = [self.tr("Line"), self.tr("Wavelength (Å)"), self.tr("f-value"), self.tr("Link")]
        self._line_table.setHorizontalHeaderLabels(headers)

    @Slot(str)
    def _on_language_changed(self, _code: str) -> None:
        self._apply_translations()

    def _connect_store_signals(self) -> None:
        self._preset_store.presets_changed.connect(self._refresh_presets)
        self._preset_store.preset_updated.connect(self._on_preset_updated)
        self._preset_store.selection_changed.connect(self._select_preset_in_list)

    def _refresh_presets(self) -> None:
        presets = self._preset_store.list_presets()
        self._preset_cache = {preset.id: preset for preset in presets}

        self._preset_list.blockSignals(True)
        self._preset_list.clear()

        tooltip = self.tr("System preset (read-only)")
        for preset in presets:
            item = QListWidgetItem(preset.name)
            item.setData(Qt.ItemDataRole.UserRole, preset.id)
            if not preset.is_editable:
                item.setForeground(QColor(Colors.TEXT_SECONDARY))
                font = item.font()
                font.setItalic(True)
                item.setFont(font)
                item.setToolTip(tooltip)
            self._preset_list.addItem(item)

        self._preset_list.blockSignals(False)
        if self._current_preset_id:
            self._select_preset_in_list(self._current_preset_id)
        self._update_action_states()

    def _select_initial_preset(self) -> None:
        current = self._preset_store.current_preset_id
        if not current and self._preset_cache:
            current = next(iter(self._preset_cache.keys()))

        if current:
            self._select_preset_in_list(current)

    @Slot(str)
    def _select_preset_in_list(self, preset_id: str | None) -> None:
        if preset_id is None:
            self._preset_list.clearSelection()
            self._current_preset_id = None
            self._populate_detail(None)
            self._update_action_states()
            return
        for index in range(self._preset_list.count()):
            item = self._preset_list.item(index)
            if item and item.data(Qt.ItemDataRole.UserRole) == preset_id:
                self._preset_list.setCurrentItem(item)
                return

    def _current_preset(self) -> Preset | None:
        return self._preset_cache.get(self._current_preset_id or "")

    def _update_action_states(self) -> None:
        preset = self._current_preset()
        is_custom = bool(preset and preset.is_editable)
        selected = self._selected_line_displays() if is_custom else []
        selected_count = len(selected)
        has_linked_selection = any(display.tie_group_uid is not None for display in selected)

        self._rename_button.setEnabled(is_custom)
        self._delete_button.setEnabled(is_custom)
        self._duplicate_button.setEnabled(preset is not None)
        self._add_line_button.setEnabled(is_custom)
        self._remove_line_button.setEnabled(is_custom and selected_count >= 1)
        self._link_button.setEnabled(is_custom and selected_count >= 2)
        self._unlink_button.setEnabled(is_custom and has_linked_selection)
        self._baseline_combo.setEnabled(is_custom and bool(preset.line_ids if preset else []))
        self._import_button.setEnabled(True)
        self._export_button.setEnabled(preset is not None)

    def _populate_detail(self, preset: Preset | None) -> None:
        previous_selection = set(self._selected_line_ids())

        self._line_table.blockSignals(True)
        self._line_table.clearContents()
        self._line_table.setRowCount(0)

        if not preset:
            self._selected_label.setText(self.tr("Selected: None"))
            self._line_count_label.setText(self.tr("Total 0 lines"))
            self._baseline_combo.clear()
            self._baseline_combo.setEnabled(False)
            self._line_table.blockSignals(False)
            self._refresh_suggestions(None)
            return

        if preset.is_editable:
            self._selected_label.setText(preset.name)
        else:
            #: {name} is the preset name; translators must keep the placeholder.
            readonly_template = self.tr("{name} (read-only)")
            self._selected_label.setText(readonly_template.format(name=preset.name))

        row_count = len(preset.line_ids)
        self._line_table.setRowCount(row_count)

        group_by_line_id = {
            line_id: group.uid for group in preset.tie_groups for line_id in group.line_ids
        }
        group_index_by_uid = {
            group.uid: index for index, group in enumerate(preset.tie_groups, start=1)
        }
        for row, line_id in enumerate(preset.line_ids):
            line = self._atomic_data.get_line_by_id(line_id)
            label = line.transition_name if line else self.tr("Unknown")
            wavelength = line.wavelength_angstrom if line else 0.0
            osc = (
                float(line.oscillator_strength)
                if line and line.oscillator_strength is not None
                else 0.0
            )
            display = _LineDisplay(
                line_id, label, wavelength, osc, line, group_by_line_id.get(line_id)
            )

            name_item = QTableWidgetItem(display.label)
            name_item.setData(Qt.ItemDataRole.UserRole, display)
            name_item.setFlags(
                (name_item.flags() | Qt.ItemFlag.ItemIsSelectable) & ~Qt.ItemFlag.ItemIsEditable
            )
            self._line_table.setItem(row, 0, name_item)

            wavelength_item = QTableWidgetItem(f"{wavelength:.4f}")
            wavelength_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            wavelength_item.setFlags(wavelength_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._line_table.setItem(row, 1, wavelength_item)

            osc_item = QTableWidgetItem(f"{osc:.6f}")
            osc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            osc_item.setFlags(osc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._line_table.setItem(row, 2, osc_item)

            group_label = "—"
            if display.tie_group_uid is not None:
                #: {index} is a 1-based group number; translators must keep the placeholder.
                group_label = self.tr("Link {index}").format(
                    index=group_index_by_uid[display.tie_group_uid]
                )
            link_item = QTableWidgetItem(group_label)
            link_item.setFlags(link_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._line_table.setItem(row, 3, link_item)

        self._restore_selection(previous_selection)
        self._line_table.blockSignals(False)

        count_template = self.tr("Total {count} lines")
        self._line_count_label.setText(count_template.format(count=row_count))

        self._configure_baseline_controls(preset)
        self._refresh_suggestions(preset)

    def _configure_baseline_controls(self, preset: Preset) -> None:
        self._updating_baseline = True
        self._baseline_combo.clear()
        self._updating_baseline = False

        if not preset.line_ids:
            self._baseline_combo.setEnabled(False)
            return

        labels: list[tuple[str, LineIdentifier]] = []
        for line_id in preset.line_ids:
            atomic_line = self._atomic_data.get_line_by_id(line_id)
            if atomic_line:
                caption = (
                    f"{atomic_line.transition_name} ({atomic_line.wavelength_angstrom:.2f} Å)"
                )
            else:
                unknown_template = self.tr("Unknown line ({id})")
                caption = unknown_template.format(id=line_id)
            labels.append((caption, line_id))

        self._updating_baseline = True
        for caption, line_id in labels:
            self._baseline_combo.addItem(caption, line_id)
        self._updating_baseline = False

        current = preset.baseline_id or preset.line_ids[0]
        index = self._baseline_combo.findData(current)
        index = max(index, 0)

        self._updating_baseline = True
        try:
            self._baseline_combo.setCurrentIndex(index)
        finally:
            self._updating_baseline = False

        self._baseline_combo.setEnabled(preset.is_editable)

    def _refresh_suggestions(self, preset: Preset | None) -> None:
        """Recompute the DB-derived link suggestions shown in the info bar."""
        suggestions = (
            suggest_preset_tie_groups(preset, self._atomic_data)
            if preset is not None and preset.is_editable
            else ()
        )
        self._current_suggestions = suggestions
        self._suggestion_bar.setVisible(bool(suggestions))
        if suggestions:
            #: {count} is the number of suggested links; translators must keep the placeholder.
            template = self.tr("{count} suggested link(s) from the line database.")
            self._suggestion_label.setText(template.format(count=len(suggestions)))

    def _selected_line_displays(self) -> list[_LineDisplay]:
        """Return the display payloads bound to the currently selected table rows."""
        displays: list[_LineDisplay] = []
        selection_model = self._line_table.selectionModel()
        if selection_model is None:
            return displays
        rows = sorted({index.row() for index in selection_model.selectedRows()})
        for row in rows:
            item = self._line_table.item(row, 0)
            display = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(display, _LineDisplay):
                displays.append(display)
        return displays

    def _selected_line_ids(self) -> list[LineIdentifier]:
        """Return line identifiers for the currently selected table rows."""
        return [display.identifier for display in self._selected_line_displays()]

    def _restore_selection(self, line_ids: set[LineIdentifier]) -> None:
        """Reselect rows matching the given identifiers after a table rebuild."""
        if not line_ids:
            return
        selection_model = self._line_table.selectionModel()
        if selection_model is None:
            return
        selection_model.clearSelection()
        flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
        for row in range(self._line_table.rowCount()):
            item = self._line_table.item(row, 0)
            display = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(display, _LineDisplay) and display.identifier in line_ids:
                selection_model.select(self._line_table.model().index(row, 0), flags)

    def _show_tie_group_issue(
        self, issue: TieGroupIssue, line_ids: Sequence[LineIdentifier] = ()
    ) -> None:
        """Show a translated message for a user-correctable group selection."""
        messages = {
            TieGroupIssue.TOO_FEW_LINES: self.tr("Select at least two lines to link."),
            TieGroupIssue.LINE_NOT_IN_PRESET: self.tr("Selected lines must belong to the preset."),
            TieGroupIssue.UNKNOWN_LINE: self.tr("Selected line is not in the database."),
            TieGroupIssue.MIXED_SPECIES: self.tr("Linked lines must have the same ion."),
            TieGroupIssue.ALREADY_GROUPED: self.tr(
                "A selected line already belongs to another link."
            ),
        }
        message = messages[issue]
        if issue is TieGroupIssue.MIXED_SPECIES:
            lines = (self._atomic_data.get_line_by_id(line_id) for line_id in line_ids)
            species = sorted({line.species for line in lines if line is not None})
            #: {species} is a comma-separated ion list; translators must keep the placeholder.
            template = self.tr("Selected ions: {species}")
            message = f"{message}\n{template.format(species=', '.join(species))}"
        QMessageBox.warning(self, self.tr("Link Error"), message)

    def _on_preset_selection_changed(self) -> None:
        selected_items = self._preset_list.selectedItems()
        if not selected_items:
            self._current_preset_id = None
            self._populate_detail(None)
            self._update_action_states()
            return

        preset_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        self._current_preset_id = _optional_string_item_data(preset_id, field_name="Preset id")
        self._populate_detail(self._current_preset())
        self._update_action_states()

    @Slot(str)
    def _on_preset_updated(self, preset_id: str) -> None:
        preset = self._preset_store.get_preset(preset_id)
        if not preset:
            return
        self._preset_cache[preset_id] = preset
        if preset_id == self._current_preset_id:
            self._populate_detail(preset)
            self._update_action_states()

    def _highlight_lines(self, line_ids: Iterable[LineIdentifier]) -> None:
        highlight = QColor(Colors.ACCENT_SELECTION_LIGHT)
        highlight.setAlpha(100)
        for row in range(self._line_table.rowCount()):
            item = self._line_table.item(row, 0)
            display = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(display, _LineDisplay) and display.identifier in line_ids:
                for col in range(self._line_table.columnCount()):
                    cell = self._line_table.item(row, col)
                    if cell:
                        cell.setBackground(highlight)
                QTimer.singleShot(3000, lambda r=row: self._clear_highlight(r))

    def _clear_highlight(self, row: int) -> None:
        if row < 0 or row >= self._line_table.rowCount():
            return
        for col in range(self._line_table.columnCount()):
            cell = self._line_table.item(row, col)
            if cell:
                cell.setBackground(Qt.GlobalColor.transparent)

    def _on_add_line(self) -> None:
        preset = self._current_preset()
        if not preset or not preset.is_editable:
            return

        dialog = LineSelectionDialog(
            self, atomic_data=self._atomic_data, existing_selection=preset.line_ids
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selection_result is not None:
            result = dialog.selection_result
            added = self._preset_store.add_lines_with_tie_groups(
                preset.id,
                result.selected_ids,
                tuple(group.line_ids for group in result.proposed_tie_groups),
            )
            if added:
                self._highlight_lines(added)
        else:
            logger.debug("Line selection dialog closed without additions")

    def _on_remove_lines(self) -> None:
        preset = self._current_preset()
        if not preset or not preset.is_editable:
            return

        targets = self._selected_line_ids()
        if not targets:
            return

        remove_template = self.tr("Remove {count} selected lines?")
        message = remove_template.format(count=len(targets))
        if (
            QMessageBox.question(
                self,
                self.tr("Confirm Removal"),
                message,
                QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        self._preset_store.remove_lines(preset.id, targets)

    def _on_link_selected_lines(self) -> None:
        """Create a new declarative tie group from the selected rows."""
        preset = self._current_preset()
        if not preset or not preset.is_editable:
            return
        line_ids = self._selected_line_ids()
        issue = validate_preset_tie_group_members(preset, line_ids, self._atomic_data)
        if issue is not None:
            self._show_tie_group_issue(issue, line_ids)
            return
        self._preset_store.add_tie_group(preset.id, line_ids)

    def _on_unlink_selected(self) -> None:
        """Remove the tie group(s) that the selected rows belong to."""
        preset = self._current_preset()
        if not preset or not preset.is_editable:
            return
        selected_ids = set(self._selected_line_ids())
        group_uids = [
            group.uid for group in preset.tie_groups if selected_ids & set(group.line_ids)
        ]
        if not group_uids:
            return
        if (
            QMessageBox.question(
                self,
                self.tr("Unlink"),
                self.tr("Remove the selected link?"),
                QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        for group_uid in group_uids:
            self._preset_store.remove_tie_group(preset.id, group_uid)

    def _on_apply_all_suggestions(self) -> None:
        """Apply every current suggestion in order, skipping invalid ones."""
        preset = self._current_preset()
        if not preset or not preset.is_editable:
            return
        for suggestion in self._current_suggestions:
            current = self._current_preset()
            if current is None or not current.is_editable:
                return
            issue = validate_preset_tie_group_members(
                current, suggestion.line_ids, self._atomic_data
            )
            if issue is not None:
                continue
            self._preset_store.add_tie_group(current.id, suggestion.line_ids)

    def _on_baseline_changed(self, index: int) -> None:
        if self._updating_baseline:
            return
        preset = self._current_preset()
        if not preset:
            return
        chosen = None if index < 0 else self._baseline_combo.itemData(index)
        selected = _optional_string_item_data(chosen, field_name="Baseline line id")
        if selected == preset.baseline_id:
            return
        try:
            self._preset_store.set_baseline(preset.id, selected)
        except (KeyError, PermissionError, ValueError) as exc:
            QMessageBox.warning(self, self.tr("Baseline Error"), str(exc))

    def _on_new_preset(self) -> None:
        name, ok = self._prompt_for_name(self.tr("New Preset"))
        if not ok:
            return

        try:
            preset = self._preset_store.create_custom_preset(name)
            self._preset_cache[preset.id] = preset
            self._select_preset_in_list(preset.id)
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Preset Error"), str(exc))
        except OverflowError as exc:
            QMessageBox.warning(self, self.tr("Preset Limit"), str(exc))

    def _on_rename_preset(self) -> None:
        preset = self._current_preset()
        if not preset or not preset.is_editable:
            return

        name, ok = self._prompt_for_name(self.tr("Rename Preset"), preset.name)
        if not ok or name == preset.name:
            return

        try:
            self._preset_store.rename_preset(preset.id, name)
        except ValueError as exc:
            QMessageBox.warning(self, self.tr("Preset Error"), str(exc))

    def _on_duplicate_preset(self) -> None:
        preset = self._current_preset()
        if not preset:
            return

        duplicate = self._preset_store.duplicate_preset(preset.id)
        self._preset_cache[duplicate.id] = duplicate
        self._select_preset_in_list(duplicate.id)

    def _on_delete_preset(self) -> None:
        preset = self._current_preset()
        if not preset or not preset.is_editable:
            return

        delete_template = self.tr("Delete preset '{name}'?")
        message = delete_template.format(name=preset.name)
        if (
            QMessageBox.warning(
                self,
                self.tr("Confirm Deletion"),
                message,
                QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        self._preset_store.delete_preset(preset.id)

    def _on_import(self) -> None:
        start_dir = self._suggest_dialog_directory()
        filter_json = self.tr("JSON Files (*.json)")
        title = self.tr("Import Presets")
        file_path, _ = QFileDialog.getOpenFileName(self, title, str(start_dir), filter_json)
        if not file_path:
            return

        try:
            summary = self._preset_store.import_presets(file_path)
        except (PresetImportError, OverflowError) as exc:
            QMessageBox.critical(self, title, str(exc))
            return

        if not summary.imported:
            QMessageBox.information(self, title, self.tr("No presets were imported."))
            return

        message, has_warnings = self._build_import_feedback(summary)
        box = QMessageBox.warning if has_warnings else QMessageBox.information
        box(self, title, message)

    def _on_export(self) -> None:
        preset = self._current_preset()
        if not preset:
            return
        title = self.tr("Export Preset")
        default_path = self._default_export_path(preset)
        filter_json = self.tr("JSON Files (*.json)")
        file_path, _ = QFileDialog.getSaveFileName(self, title, str(default_path), filter_json)
        if not file_path:
            return

        destination = Path(file_path)
        if destination.suffix.lower() != ".json":
            destination = destination.with_suffix(".json")

        try:
            final_path = self._preset_store.export_presets(destination, [preset.id])
        except (PresetExportError, OSError) as exc:  # pragma: no cover - filesystem dependent
            QMessageBox.critical(self, title, str(exc))
            return

        template = self.tr("Preset '{name}' exported to {path}")
        message = template.format(name=preset.name, path=str(final_path))
        QMessageBox.information(self, title, message)

    def _prompt_for_name(self, title: str, default: str = "") -> tuple[str, bool]:
        text, ok = QInputDialog.getText(self, title, self.tr("Enter preset name:"), text=default)
        return text.strip(), bool(ok) and bool(text.strip())

    def _suggest_dialog_directory(self) -> Path:
        try:
            return Path.home()
        except (OSError, RuntimeError):  # pragma: no cover - platform dependent
            return Path.cwd()

    def _default_export_path(self, preset: Preset) -> Path:
        directory = self._suggest_dialog_directory()
        sanitized = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in preset.name
        ).strip("._")
        if not sanitized:
            sanitized = "preset"
        return directory / f"{sanitized}.json"

    def _build_import_feedback(self, summary: PresetImportSummary) -> tuple[str, bool]:
        summary_template = self.tr("Imported {count} preset(s).")
        lines: list[str] = [summary_template.format(count=len(summary.imported))]
        has_warnings = False

        if summary.renamed:
            pairs = []
            for old_name, new_name in summary.renamed:
                if not old_name or old_name == new_name:
                    pairs.append(new_name)
                else:
                    rename_template = self.tr("{old} -> {new}")
                    pairs.append(rename_template.format(old=old_name, new=new_name))
            renamed_template = self.tr("Renamed duplicates: {pairs}")
            lines.append(renamed_template.format(pairs=", ".join(pairs)))
            has_warnings = True

        if summary.skipped:
            skipped_template = self.tr("Skipped {count} preset(s) with no valid lines.")
            lines.append(skipped_template.format(count=summary.skipped))
            has_warnings = True

        if summary.missing_lines:
            has_warnings = True
            lines.append(self.tr("Missing line IDs were ignored:"))
            max_entries = 3
            items = list(summary.missing_lines.items())
            for index, (name, missing_ids) in enumerate(items):
                if index >= max_entries:
                    remaining = len(items) - max_entries
                    if remaining > 0:
                        missing_more_template = self.tr("... and {count} more preset(s).")
                        lines.append(missing_more_template.format(count=remaining))
                    break
                preview = ", ".join(missing_ids[:MISSING_LINE_PREVIEW_LIMIT])
                if len(missing_ids) > MISSING_LINE_PREVIEW_LIMIT:
                    preview += ", ..."
                missing_entry_template = self.tr("- {name}: {ids}")
                lines.append(missing_entry_template.format(name=name, ids=preview))

        return "\n".join(lines), has_warnings


__all__ = ["PresetListDialog"]
