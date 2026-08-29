"""Dialog for selecting spectral lines from the spectral database (SCR-DIA-SDB)."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Iterator  # noqa: TC003
from contextlib import contextmanager
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Slot
from PySide6.QtGui import QBrush, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)
from shiboken6 import isValid

from chappy.application.line_selection import LineSelectionResult, LineSelectionSession
from chappy.core.atomic_data import (
    AtomicLine,
    AtomicLineData,
    charge_to_stage,
    normalize_element_symbol,
)
from chappy.gui.dialog_sizing import enforce_translated_minimum_size
from chappy.gui.dialogs.line_selection_dialog_builder import (
    LineSelectionDialogBuilder,
    _LineSelectionModeStatePort,
    validate_mode_state,
)
from chappy.gui.theme import Colors
from chappy.gui.visual_tokens import DialogMetrics
from chappy.i18n import LanguageSwitcher, get_language_switcher
from chappy.presentation.line_selection.filter import (
    LineFilterStatus,
    LineSearchCriteria,
    LineSelectionFilterEvaluator,
)
from chappy.presentation.line_selection.presenter import (
    LinePreviewLabels,
    LinePreviewPresenter,
    LineRowLabels,
    LineRowPayload,
    LineSelectionPresenter,
    RowHighlightRole,
)

logger = logging.getLogger(__name__)


type SortKey = tuple[object, object, object]


@dataclass(frozen=True, slots=True)
class _WavelengthDraft:
    """Parsed state of one optional wavelength field."""

    value: float | None
    is_valid: bool


class _SortAwareItem(QTableWidgetItem):
    """Table item that sorts using a custom key when available."""

    def __init__(self, text: str, *, sort_key: SortKey | None = None) -> None:
        super().__init__(text)
        self._sort_key: SortKey | None = sort_key

    def set_sort_key(self, sort_key: SortKey | None) -> None:
        self._sort_key = sort_key

    def __lt__(self, other: object) -> bool:
        if (
            isinstance(other, _SortAwareItem)
            and self._sort_key is not None
            and other._sort_key is not None
        ):
            return self._sort_key < other._sort_key
        if isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        return False


class _SortAwareCheckItem(_SortAwareItem):
    """Checkbox column item that sorts by selection state."""

    def __init__(
        self, text: str, *, sort_key: SortKey | None = None, is_checked: bool = False
    ) -> None:
        super().__init__(text, sort_key=sort_key)
        self._is_checked = is_checked

    def set_checked(self, checked: bool) -> None:
        self._is_checked = checked

    def _status(self) -> tuple[int]:
        checked_flag = 0 if self._is_checked else 1
        return (checked_flag,)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, _SortAwareCheckItem):
            status_self = self._status()
            status_other = other._status()
            if status_self != status_other:
                return status_self < status_other
        return super().__lt__(other)


class LineSelectionDialog(QDialog):
    """Modal dialog used to search and select spectral lines."""

    def __init__(
        self,
        parent: QWidget | None = None,
        mode_state: _LineSelectionModeStatePort | None = None,
        *,
        atomic_data: AtomicLineData,
        existing_selection: Iterable[str] | None = None,
        initial_selection: Iterable[str] | None = None,
    ) -> None:
        """Create the dialog with optional pre-selected line identifiers."""
        super().__init__(parent)

        self._language_switcher: LanguageSwitcher = get_language_switcher(self)

        self.atomic_data = atomic_data
        self.mode_state = validate_mode_state(mode_state)
        self._selection_presenter = LineSelectionPresenter()
        self._preview_presenter = LinePreviewPresenter()
        self._filter_evaluator = LineSelectionFilterEvaluator(self.atomic_data)

        self._session = LineSelectionSession(
            self.atomic_data,
            existing_ids=set(existing_selection or []),
            initial_ids=set(initial_selection or []),
        )
        self._selection_result: LineSelectionResult | None = None

        self._filtered_lines: list[AtomicLine] = []
        self._line_lookup = {line.line_id: line for line in self.atomic_data.lines}
        self._focused_line: AtomicLine | None = None
        self._suppress_table_updates = False
        self._existing_row_color = QColor(Colors.UI_ACCENT_MUTED)

        self._sort_column: int = 2
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(250)
        self._filter_timer.timeout.connect(self._apply_filters)

        self._last_applied_filters: LineSearchCriteria | None = None
        self._last_applied_wavelength_texts = ("", "")
        self._accepted_element = ""
        self._user_resized_columns = False
        self._suppress_header_resize = False

        self._setup_window()
        widgets = LineSelectionDialogBuilder().build(
            self,
            mode_state=self.mode_state,
            ok_initially_enabled=bool(self._session.selected_ids),
            sort_column=self._sort_column,
            sort_order=self._sort_order,
        )
        self._keyword_edit = widgets.keyword_edit
        self._element_combo = widgets.element_combo
        self._stage_combo = widgets.stage_combo
        self._wavelength_min = widgets.wavelength_min
        self._wavelength_max = widgets.wavelength_max
        self._filter_warning = widgets.filter_warning
        self._clear_filters_button = widgets.clear_filters_button
        self._result_label = widgets.result_label
        self._result_helper_label = widgets.result_helper_label
        self._table = widgets.table
        self._preview = widgets.preview
        self._selection_label = widgets.selection_label
        self._selection_list = widgets.selection_list
        self._selection_placeholder = widgets.selection_placeholder
        self._selection_stack = widgets.selection_stack
        self._remove_selection_button = widgets.remove_selection_button
        self._clear_selection_button = widgets.clear_selection_button
        self._button_box = widgets.button_box
        self._group_selection_combo = widgets.group_selection_combo

        self._set_table_headers()
        self._connect_signals()
        self._load_initial_data()
        enforce_translated_minimum_size(self, floor=QSize(*DialogMetrics.MIN_SIZE_LINE_SELECTION))

        self._language_switcher.language_changed.connect(self._on_language_changed)

    def _setup_window(self) -> None:
        """Configure window-level properties for the dialog."""
        self.setModal(True)
        self.setObjectName("spectralDatabaseDialog")
        self.setWindowTitle(self.tr("Line Database Search"))
        self.setSizeGripEnabled(True)

    def _column_headers(self) -> list[str]:
        return [
            "",
            self.tr("Line"),
            self.tr("Wavelength (Å)"),
            self.tr("f-value"),
            self.tr("Γ (s⁻¹)"),
        ]

    def _set_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels(self._column_headers())
        header = self._table.horizontalHeader()
        header.setSortIndicator(self._sort_column, self._sort_order)
        self._apply_column_width_constraints()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Handle table key events to toggle selection shortcuts.

        Args:
            obj: Object receiving the event.
            event: Event forwarded for filtering.

        Returns:
            True if the event was consumed.
        """
        if (
            obj is self._table
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Space
            and self._handle_space_toggle()
        ):
            return True
        if (
            event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Escape
        ):
            if obj is self._element_combo.lineEdit():
                self._restore_element_draft()
                return True
            if obj is self._wavelength_min:
                self._wavelength_min.setText(self._last_applied_wavelength_texts[0])
                self._apply_filters()
                return True
            if obj is self._wavelength_max:
                self._wavelength_max.setText(self._last_applied_wavelength_texts[1])
                self._apply_filters()
                return True
        return super().eventFilter(obj, event)

    @contextmanager
    def _suppress_table_change_signals(self) -> Iterator[None]:
        previous_state = self._suppress_table_updates
        self._suppress_table_updates = True
        try:
            yield
        finally:
            self._suppress_table_updates = previous_state

    def _handle_space_toggle(self) -> bool:
        selection_model = self._table.selectionModel()
        target_rows = (
            [index.row() for index in selection_model.selectedRows()] if selection_model else []
        )

        current_row = self._table.currentRow()
        if current_row >= 0 and current_row not in target_rows:
            target_rows.append(current_row)

        handled = False
        for row in target_rows:
            handled = self._toggle_selection_for_row(row) or handled
        return handled

    def _connect_signals(self) -> None:
        self._keyword_edit.textChanged.connect(self._schedule_filter_update)
        self._element_combo.currentIndexChanged.connect(self._on_element_changed)
        self._stage_combo.currentIndexChanged.connect(self._apply_filters)
        element_edit = self._element_combo.lineEdit()
        if element_edit is None:
            msg = "Editable element combo must expose a line edit"
            raise RuntimeError(msg)
        element_edit.textEdited.connect(self._schedule_filter_update)
        element_edit.editingFinished.connect(self._apply_filters)
        element_edit.installEventFilter(self)
        for field in (self._wavelength_min, self._wavelength_max):
            field.textEdited.connect(self._schedule_filter_update)
            field.editingFinished.connect(self._apply_filters)
            field.installEventFilter(self)

        self._clear_filters_button.clicked.connect(self._reset_filters)
        self._clear_selection_button.clicked.connect(self._clear_selection)

        self._selection_list.currentItemChanged.connect(self._on_selection_list_current_changed)
        self._remove_selection_button.clicked.connect(self._on_remove_selection_clicked)

        header = self._table.horizontalHeader()
        header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)
        header.sectionResized.connect(self._on_header_section_resized)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.installEventFilter(self)

        self._button_box.accepted.connect(self._finalize_selection)
        self._button_box.rejected.connect(self.reject)

    def _load_initial_data(self) -> None:
        self._element_combo.blockSignals(True)
        self._element_combo.clear()
        self._element_combo.addItem(self.tr("All"), "")
        for element in self.atomic_data.get_available_elements():
            display_symbol = normalize_element_symbol(element) or element
            self._element_combo.addItem(display_symbol, element.upper())
        self._element_combo.setCurrentIndex(-1)
        self._element_combo.blockSignals(False)

        self._accepted_element = ""
        self._refresh_charge_combo("")
        self._apply_filters()

    @Slot(int)
    def _on_element_changed(self, index: int) -> None:
        if index < 0:
            self._schedule_filter_update()
            return
        element = self._element_combo.itemData(index)
        if not isinstance(element, str):
            msg = "Element combo item data must be a string"
            raise TypeError(msg)
        self._accept_element(element)
        self._apply_filters()

    def _refresh_charge_combo(self, element: str) -> None:
        charge_states = self.atomic_data.get_available_charge_states(element or None)

        self._stage_combo.blockSignals(True)
        self._stage_combo.clear()
        self._stage_combo.addItem(self.tr("All"), None)
        for state in charge_states:
            stage = charge_to_stage(state)
            self._stage_combo.addItem(stage or str(state + 1), state)
        self._stage_combo.blockSignals(False)

    def _accept_element(self, element: str) -> None:
        if element == self._accepted_element:
            return
        self._accepted_element = element
        self._refresh_charge_combo(element)

    @Slot()
    def _schedule_filter_update(self) -> None:
        self._filter_timer.start()

    @Slot()
    def _apply_filters(self) -> None:
        if self._filter_timer.isActive():
            self._filter_timer.stop()

        keyword = self._keyword_edit.text().strip()
        element = self._resolve_element_draft()
        if element is None:
            self._show_filter_error(
                self.tr("Select an element from the suggestions."), (self._element_combo,)
            )
            return
        self._accept_element(element)

        charge_state = self._stage_combo.currentData()
        if charge_state is not None and not isinstance(charge_state, int):
            msg = "Ion-stage combo item data must be an integer or None"
            raise TypeError(msg)

        minimum = self._parse_wavelength(self._wavelength_min)
        maximum = self._parse_wavelength(self._wavelength_max)
        invalid_fields = tuple(
            field
            for field, draft in ((self._wavelength_min, minimum), (self._wavelength_max, maximum))
            if not draft.is_valid
        )
        if invalid_fields:
            self._show_filter_error(
                self.tr("Enter a wavelength from 0 to 50,000 Å."), invalid_fields
            )
            return

        criteria = LineSearchCriteria(
            keyword=keyword,
            element=element,
            charge_state=charge_state,
            wavelength_min=minimum.value,
            wavelength_max=maximum.value,
        )

        result = self._filter_evaluator.evaluate(criteria, self._last_applied_filters)

        if result.status is LineFilterStatus.INVALID_RANGE:
            self._show_filter_error(
                self.tr("Minimum wavelength exceeds the maximum."),
                (self._wavelength_min, self._wavelength_max),
            )
            return
        self._clear_filter_error()

        if result.status is LineFilterStatus.UNCHANGED:
            return

        self._filtered_lines = list(result.lines)
        self._populate_table()
        self._update_result_summary()
        self._update_selection_summary()

        self._last_applied_filters = criteria
        self._last_applied_wavelength_texts = (
            self._wavelength_min.text(),
            self._wavelength_max.text(),
        )

    def _resolve_element_draft(self) -> str | None:
        text = self._element_combo.currentText().strip()
        if not text:
            self._element_combo.blockSignals(True)
            self._element_combo.setCurrentIndex(-1)
            self._element_combo.blockSignals(False)
            return ""

        prefix_matches: list[int] = []
        exact_match: int | None = None
        for index in range(self._element_combo.count()):
            display = self._element_combo.itemText(index)
            if display.casefold() == text.casefold():
                exact_match = index
                break
            data = self._element_combo.itemData(index)
            if isinstance(data, str) and data and display.casefold().startswith(text.casefold()):
                prefix_matches.append(index)

        match_index = exact_match
        if match_index is None and len(prefix_matches) == 1:
            match_index = prefix_matches[0]
        if match_index is None:
            return None

        data = self._element_combo.itemData(match_index)
        if not isinstance(data, str):
            msg = "Element combo item data must be a string"
            raise TypeError(msg)
        self._element_combo.blockSignals(True)
        self._element_combo.setCurrentIndex(match_index)
        self._element_combo.blockSignals(False)
        return data

    def _restore_element_draft(self) -> None:
        self._element_combo.blockSignals(True)
        if self._accepted_element:
            index = self._element_combo.findData(self._accepted_element)
            if index < 0:
                msg = f"Accepted element is missing from combo: {self._accepted_element}"
                raise RuntimeError(msg)
            self._element_combo.setCurrentIndex(index)
        else:
            self._element_combo.setCurrentIndex(-1)
            element_edit = self._element_combo.lineEdit()
            if element_edit is None:
                msg = "Editable element combo must expose a line edit"
                raise RuntimeError(msg)
            element_edit.clear()
        self._element_combo.blockSignals(False)
        self._apply_filters()

    @staticmethod
    def _parse_wavelength(field: QLineEdit) -> _WavelengthDraft:
        text = field.text().strip()
        if not text:
            return _WavelengthDraft(value=None, is_valid=True)
        if not field.hasAcceptableInput():
            return _WavelengthDraft(value=None, is_valid=False)
        value, parsed = field.locale().toDouble(text)
        if not parsed or not math.isfinite(value):
            return _WavelengthDraft(value=None, is_valid=False)
        return _WavelengthDraft(value=value, is_valid=True)

    def _show_filter_error(self, message: str, fields: tuple[QWidget, ...]) -> None:
        self._clear_filter_error()
        for field in fields:
            self._set_error_property(field, True)
            field.setAccessibleDescription(message)
        self._filter_warning.setText(message)
        self._filter_warning.setAccessibleDescription(message)
        self._filter_warning.show()

    def _clear_filter_error(self) -> None:
        for field in (self._element_combo, self._wavelength_min, self._wavelength_max):
            self._set_error_property(field, False)
            field.setAccessibleDescription("")
        self._filter_warning.hide()
        self._filter_warning.setText("")
        self._filter_warning.setAccessibleDescription("")

    @staticmethod
    def _set_error_property(field: QWidget, error: bool) -> None:
        field.setProperty("error", error)
        field.style().unpolish(field)
        field.style().polish(field)
        field.update()

    def _on_language_changed(self, _code: str) -> None:
        self._element_combo.setItemText(0, self.tr("All"))
        element_edit = self._element_combo.lineEdit()
        if element_edit is None:
            msg = "Editable element combo must expose a line edit"
            raise RuntimeError(msg)
        element_edit.setPlaceholderText(self.tr("All elements"))
        self._wavelength_min.setPlaceholderText(self.tr("No minimum"))
        self._wavelength_max.setPlaceholderText(self.tr("No maximum"))
        self._set_table_headers()
        enforce_translated_minimum_size(self, floor=QSize(*DialogMetrics.MIN_SIZE_LINE_SELECTION))

    def _refresh_after_selection_change(self) -> None:
        """Re-sync checkbox states, highlights, and summary after a selection change."""
        self._refresh_selection_visuals()
        self._update_selection_summary()

    def _row_labels(self) -> LineRowLabels:
        """Return translated labels used to build result-table rows."""
        return LineRowLabels(
            multiplet_header=self.tr("Multiplet"),
            multiplet_tooltip=self.tr("Selecting one component will select the entire multiplet."),
        )

    def _refresh_selection_visuals(self) -> None:
        """Update every row's checkbox state and highlight from the current selection."""
        with self._suppress_table_change_signals():
            for row in range(self._table.rowCount()):
                checkbox_item = self._table.item(row, 0)
                line = self._line_from_row(row)
                if checkbox_item is None or line is None:
                    continue
                aggregated = self._session.is_aggregated_selected(line)
                checkbox_item.setCheckState(
                    Qt.CheckState.Checked if aggregated else Qt.CheckState.Unchecked
                )
                if isinstance(checkbox_item, _SortAwareCheckItem):
                    checkbox_item.set_checked(aggregated)
            self._apply_highlights()

    def _populate_table(self) -> None:
        sorting_was_enabled = self._table.isSortingEnabled()
        if sorting_was_enabled:
            self._table.setSortingEnabled(False)

        payloads = self._selection_presenter.build_row_payloads(
            self._filtered_lines, selection=self._session, labels=self._row_labels()
        )
        existing_tooltip = self.tr("This line is already selected.")

        with self._suppress_table_change_signals():
            self._table.clearContents()
            self._table.setRowCount(len(self._filtered_lines))

            for row, (line, payload) in enumerate(
                zip(self._filtered_lines, payloads, strict=True)
            ):
                self._populate_row(row, line, payload, existing_tooltip)

        if sorting_was_enabled:
            self._table.setSortingEnabled(True)

        self._apply_current_sort()
        self._apply_column_width_constraints()
        self._apply_highlights()

    def _populate_row(
        self, row: int, line: AtomicLine, payload: LineRowPayload, existing_tooltip: str
    ) -> None:
        """Build and install the table items for a single result row."""
        checkbox_item = _SortAwareCheckItem("", is_checked=payload.aggregated_selected)
        if payload.is_selectable:
            checkbox_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
        else:
            checkbox_item.setFlags(Qt.ItemFlag.NoItemFlags)
        checkbox_item.setCheckState(
            Qt.CheckState.Checked if payload.aggregated_selected else Qt.CheckState.Unchecked
        )
        checkbox_item.set_sort_key(payload.selection_sort_key)
        checkbox_item.setData(Qt.ItemDataRole.UserRole, payload.line_id)
        self._table.setItem(row, 0, checkbox_item)

        name_item = _SortAwareItem(payload.display_name, sort_key=payload.name_sort_key)
        name_item.setData(Qt.ItemDataRole.UserRole, line)
        if payload.accessible_text:
            name_item.setData(Qt.ItemDataRole.AccessibleTextRole, payload.accessible_text)
        if payload.name_tooltip:
            name_item.setToolTip(payload.name_tooltip)
        self._table.setItem(row, 1, name_item)

        wavelength_item = _SortAwareItem(
            payload.wavelength_text, sort_key=payload.wavelength_sort_key
        )
        wavelength_item.setData(Qt.ItemDataRole.UserRole, payload.wavelength_value)
        self._table.setItem(row, 2, wavelength_item)

        f_item = _SortAwareItem(payload.f_value_text, sort_key=payload.f_value_sort_key)
        f_item.setData(Qt.ItemDataRole.UserRole, payload.f_value)
        self._table.setItem(row, 3, f_item)

        gamma_item = _SortAwareItem(payload.gamma_text, sort_key=payload.gamma_sort_key)
        gamma_item.setData(Qt.ItemDataRole.UserRole, payload.gamma_value)
        self._table.setItem(row, 4, gamma_item)

        if payload.is_existing:
            # Backgrounds for existing rows are painted by ``_apply_highlights``
            # (EXISTING role); only the tooltip needs to be set here.
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                if item:
                    item.setToolTip(existing_tooltip)

    def _apply_current_sort(self) -> None:
        header = self._table.horizontalHeader()
        self._table.sortItems(self._sort_column, self._sort_order)
        header.setSortIndicator(self._sort_column, self._sort_order)

    @Slot(int, Qt.SortOrder)
    def _on_sort_indicator_changed(self, column: int, order: Qt.SortOrder) -> None:
        self._sort_column = column
        self._sort_order = order

    def _on_header_section_resized(self, index: int, _old: int, _new: int) -> None:
        if self._suppress_header_resize:
            return
        if index >= 0:
            self._user_resized_columns = True

    def _apply_column_width_constraints(self) -> None:
        header = self._table.horizontalHeader()
        if header.count() < self._table.columnCount() or self._user_resized_columns:
            return

        self._suppress_header_resize = True
        try:
            width_caps = {2: 130, 3: 110, 4: 130}

            for column, cap in width_caps.items():
                self._table.resizeColumnToContents(column)
                current = header.sectionSize(column)
                header.resizeSection(column, min(max(current, 60), cap))

            self._table.resizeColumnToContents(1)
            name_width = header.sectionSize(1)
            header.resizeSection(1, min(max(name_width, 130), 240))
        finally:
            self._suppress_header_resize = False

    def _update_result_summary(self) -> None:
        existing_ids = self._session.existing_ids
        existing_in_view = sum(1 for line in self._filtered_lines if line.line_id in existing_ids)
        #: {count} is the number of result lines; translators must keep the placeholder.
        result_count_template = self.tr("{count} lines")
        text = result_count_template.format(count=len(self._filtered_lines))
        if existing_in_view:
            result_existing_template = self.tr(" (including {count} already selected)")
            text += result_existing_template.format(count=existing_in_view)
        self._result_label.setText(text)

    def _update_selection_summary(self) -> None:
        total_selected = len(self._session.selected_ids)
        selection_count_template = self.tr("{count} lines")
        self._selection_label.setText(selection_count_template.format(count=total_selected))
        if isValid(self._button_box):
            ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
            if ok_button and isValid(ok_button):
                ok_button.setEnabled(bool(total_selected) or bool(self._focused_line))
        self._refresh_selection_list()

    def _refresh_selection_list(self) -> None:
        current_id: str | None = None
        current_item = self._selection_list.currentItem()
        if current_item is not None:
            data = current_item.data(Qt.ItemDataRole.UserRole)
            current_id = data if isinstance(data, str) else None

        self._selection_list.blockSignals(True)
        self._selection_list.clear()

        sorted_ids = sorted(self._session.selected_ids, key=self._selection_list_sort_key)
        for line_id in sorted_ids:
            line = self._line_lookup.get(line_id)
            if not line:
                continue
            list_item = QListWidgetItem(line.transition_name)
            list_item.setData(Qt.ItemDataRole.UserRole, line_id)
            self._selection_list.addItem(list_item)
            if current_id and line_id == current_id:
                self._selection_list.setCurrentItem(list_item)

        self._selection_list.blockSignals(False)

        if self._selection_list.count() > 0 and self._selection_list.currentRow() == -1:
            self._selection_list.setCurrentRow(0)

        if self._selection_list.count() == 0:
            self._selection_stack.setCurrentWidget(self._selection_placeholder)
        else:
            self._selection_stack.setCurrentWidget(self._selection_list)

    def _selection_list_sort_key(self, line_id: str) -> tuple[float, str, str]:
        line = self._line_lookup.get(line_id)
        if not line:
            return (float("inf"), line_id, line_id)
        return (float(line.wavelength_angstrom), line.transition_name, line_id)

    def _on_selection_list_current_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if not current:
            return
        line_id = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(line_id, str):
            return
        line = self._line_lookup.get(line_id)
        if not line:
            return
        self._focused_line = line
        self._update_preview(line)

    def _on_remove_selection_clicked(self) -> None:
        item = self._selection_list.currentItem()
        if item is None:
            return
        line_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(line_id, str):
            return

        change = self._session.remove(line_id)
        if not change.changed_line_ids:
            return
        self._refresh_after_selection_change()

    def _toggle_selection_for_row(self, row: int) -> bool:
        line = self._line_from_row(row)
        if not line:
            return False
        if line.line_id in self._session.existing_ids:
            self._focused_line = line
            self._update_preview(line)
            return False

        self._session.toggle(line.line_id)
        self._focused_line = line
        self._refresh_after_selection_change()
        self._update_preview(line)
        return True

    @Slot(int, int)
    def _on_cell_clicked(self, row: int, _column: int) -> None:
        line = self._line_from_row(row)
        if not line:
            return
        self._focused_line = line
        self._update_preview(line)

    @Slot(int, int)
    def _on_cell_double_clicked(self, row: int, _column: int) -> None:
        line = self._line_from_row(row)
        if not line:
            return
        self._focused_line = line
        if not self._toggle_selection_for_row(row):
            self._update_preview(line)

    @Slot(QTableWidgetItem)
    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suppress_table_updates or not item or item.column() != 0:
            return
        line_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(line_id, str) or line_id in self._session.existing_ids:
            return
        self._session.toggle(line_id)
        self._refresh_after_selection_change()

    def _line_from_row(self, row: int) -> AtomicLine | None:
        item = self._table.item(row, 1)
        if not item:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, AtomicLine):
            return data
        return None

    def _ordered_lines(self) -> list[tuple[int, AtomicLine]]:
        """Return (row, line) pairs in current display order."""
        pairs: list[tuple[int, AtomicLine]] = []
        for row in range(self._table.rowCount()):
            line = self._line_from_row(row)
            if line is not None:
                pairs.append((row, line))
        return pairs

    def _apply_highlights(self) -> None:
        """Repaint row backgrounds from the current selection (full, idempotent)."""
        rows_lines = self._ordered_lines()
        roles = self._selection_presenter.build_highlight_states(
            [line for _row, line in rows_lines], selection=self._session
        )
        brushes = self._highlight_brushes()
        # ``setBackground`` emits ``itemChanged`` for column 0, which would be
        # misread as a user toggle; suppress table-change handling while painting.
        with self._suppress_table_change_signals():
            for (row, _line), role in zip(rows_lines, roles, strict=True):
                brush = brushes[role]
                for col in range(self._table.columnCount()):
                    item = self._table.item(row, col)
                    if item is not None:
                        item.setBackground(brush)

    def _highlight_brushes(self) -> dict[RowHighlightRole, QBrush]:
        """Map each highlight role to its background brush."""
        highlight_color = QColor(Colors.ACCENT_SELECTION_LIGHT)
        highlight_color.setAlpha(110)
        group_header_color = QColor(Colors.UI_ACCENT_MUTED)
        group_header_color.setAlpha(55)
        return {
            RowHighlightRole.EXISTING: QBrush(self._existing_row_color),
            RowHighlightRole.HIGHLIGHT: QBrush(highlight_color),
            RowHighlightRole.GROUP_HEADER: QBrush(group_header_color),
            RowHighlightRole.NONE: QBrush(),
        }

    def _update_preview(self, line: AtomicLine) -> None:
        self._preview.setHtml(
            self._preview_presenter.render_preview_html(line, labels=self._preview_labels())
        )

    def _preview_labels(self) -> LinePreviewLabels:
        """Return translated labels for the line preview presenter."""
        return LinePreviewLabels(
            element=self.tr("Element"),
            ion_stage=self.tr("Ion stage"),
            species=self.tr("Species"),
            multiplet=self.tr("Multiplet"),
            component=self.tr("Component"),
            rest_wavelength=self.tr("Rest wavelength"),
            ritz_wavelength=self.tr("Ritz wavelength"),
            ritz_uncertainty=self.tr("Ritz uncertainty"),
            observed_wavelength=self.tr("Observed wavelength"),
            observed_uncertainty=self.tr("Observed uncertainty"),
            source=self.tr("Source"),
            oscillator_f=self.tr("Oscillator f"),
            gamma=self.tr("Gamma (s⁻¹)"),
            lower_level_ev=self.tr("Lower level (eV)"),
            upper_level_ev=self.tr("Upper level (eV)"),
            delta_e_ev=self.tr("Delta E (eV)"),
            lower_level=self.tr("Lower level"),
            upper_level=self.tr("Upper level"),
            accuracy=self.tr("Accuracy"),
            transition_ref=self.tr("Transition ref"),
            wavelength_ref=self.tr("Wavelength ref"),
            notes=self.tr("Notes"),
            basic_information=self.tr("Basic information"),
            wavelength_strength=self.tr("Wavelength & strength"),
            energy_levels=self.tr("Energy levels"),
            references=self.tr("References"),
            source_ritz=self.tr("Ritz"),
            source_observed=self.tr("Observed"),
            source_aggregated=self.tr("Aggregated"),
            source_custom=self.tr("Custom"),
        )

    @Slot()
    def _reset_filters(self) -> None:
        self._filter_timer.stop()
        self._keyword_edit.blockSignals(True)
        self._keyword_edit.clear()
        self._keyword_edit.blockSignals(False)
        self._element_combo.blockSignals(True)
        self._element_combo.setCurrentIndex(-1)
        element_edit = self._element_combo.lineEdit()
        if element_edit is None:
            msg = "Editable element combo must expose a line edit"
            raise RuntimeError(msg)
        element_edit.clear()
        self._element_combo.blockSignals(False)
        self._accepted_element = ""
        self._refresh_charge_combo("")
        self._wavelength_min.clear()
        self._wavelength_max.clear()
        self._last_applied_filters = None
        self._last_applied_wavelength_texts = ("", "")
        self._apply_filters()

    @Slot()
    def _clear_selection(self) -> None:
        if not self._session.selected_ids:
            return
        self._session.clear()
        self._refresh_after_selection_change()

    def _finalize_selection(self) -> None:
        if (
            not self._session.selected_ids
            and self._focused_line is not None
            and self._focused_line.line_id not in self._session.existing_ids
        ):
            self._session.toggle(self._focused_line.line_id)

        self._selection_result = self._session.build_result()
        selected_lines: list[AtomicLine] = []

        for line_id in self._selection_result.selected_ids:
            line = self.atomic_data.get_line_by_id(line_id)
            if line:
                selected_lines.append(line)

        if not selected_lines:
            QMessageBox.information(
                self,
                self.tr("No lines selected"),
                self.tr("Check the lines to add or select a row."),
            )
            return

        table_blocked = False
        if isValid(self._table) and not self._table.signalsBlocked():
            self._table.blockSignals(True)
            table_blocked = True

        try:
            self.accept()
        finally:
            if table_blocked and isValid(self._table):
                self._table.blockSignals(False)

    @property
    def selection_result(self) -> LineSelectionResult | None:
        """Return the accepted selection result, including group proposals."""
        return self._selection_result
