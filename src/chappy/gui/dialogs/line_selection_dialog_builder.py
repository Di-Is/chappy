"""UI construction for :class:`LineSelectionDialog`.

This module owns the widget tree of the line database search dialog. Keeping it
separate lets the dialog focus on signal wiring and selection-state coordination
while the builder concentrates on layout and styling.

Note on i18n: ``QObject.tr`` resolves its translation context from the calling
class. To keep the existing ``LineSelectionDialog`` translation context valid for
both runtime lookup and ``pyside6-lupdate`` extraction, strings created here use
``QCoreApplication.translate("LineSelectionDialog", ...)`` explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import override

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QDoubleValidator, QValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QStackedLayout,
    QStyle,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.theme import (
    Colors,
    apply_action_row_sizing,
    apply_button_variant,
    empty_state_label_style,
)


class _CorrectableDoubleValidator(QDoubleValidator):
    """Keep invalid numeric drafts editable until the dialog validates them."""

    @override
    def validate(self, input_text: str, position: int) -> object:
        result = super().validate(input_text, position)
        if not isinstance(result, tuple) or len(result) != 3:
            msg = "QDoubleValidator.validate() returned an invalid result"
            raise RuntimeError(msg)
        state, normalized, normalized_position = result
        if (
            not isinstance(state, QValidator.State)
            or not isinstance(normalized, str)
            or not isinstance(normalized_position, int)
        ):
            msg = "QDoubleValidator.validate() returned invalid result types"
            raise TypeError(msg)
        if state is QValidator.State.Invalid:
            state = QValidator.State.Intermediate
        return state, normalized, normalized_position


@dataclass(frozen=True, slots=True)
class LineSelectionWidgets:
    """Widgets produced when building the line selection dialog."""

    keyword_edit: QLineEdit
    element_combo: QComboBox
    stage_combo: QComboBox
    wavelength_min: QLineEdit
    wavelength_max: QLineEdit
    filter_warning: QLabel
    clear_filters_button: QPushButton
    result_label: QLabel
    result_helper_label: QLabel
    table: QTableWidget
    preview: QTextEdit
    selection_label: QLabel
    selection_list: QListWidget
    selection_placeholder: QLabel
    selection_stack: QStackedLayout
    remove_selection_button: QPushButton
    clear_selection_button: QPushButton
    button_box: QDialogButtonBox


@dataclass(frozen=True, slots=True)
class _FilterSection:
    """Filter bar group box and its interactive widgets."""

    panel: QGroupBox
    keyword_edit: QLineEdit
    element_combo: QComboBox
    stage_combo: QComboBox
    wavelength_min: QLineEdit
    wavelength_max: QLineEdit
    filter_warning: QLabel
    clear_filters_button: QPushButton


@dataclass(frozen=True, slots=True)
class _ResultsSection:
    """Results group box and its widgets."""

    group: QGroupBox
    table: QTableWidget
    result_label: QLabel
    result_helper_label: QLabel


@dataclass(frozen=True, slots=True)
class _DetailSection:
    """Line detail group box and its widgets."""

    group: QGroupBox
    preview: QTextEdit


@dataclass(frozen=True, slots=True)
class _SelectionSection:
    """Selection group box and its widgets."""

    group: QGroupBox
    selection_label: QLabel
    selection_list: QListWidget
    selection_placeholder: QLabel
    selection_stack: QStackedLayout
    remove_selection_button: QPushButton
    clear_selection_button: QPushButton


class LineSelectionDialogBuilder:
    """Builds the widget tree for :class:`LineSelectionDialog`."""

    def __init__(self) -> None:
        """Initialize transient build state."""
        self._host: QWidget
        self._sort_column: int = 0
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

    def build(
        self,
        host: QWidget,
        *,
        ok_initially_enabled: bool,
        sort_column: int,
        sort_order: Qt.SortOrder,
    ) -> LineSelectionWidgets:
        """Assemble the dialog content layout on ``host``.

        Args:
            host: Dialog widget that receives the top-level layout.
            ok_initially_enabled: Initial enabled state for the OK button.
            sort_column: Column used for the initial sort indicator.
            sort_order: Order used for the initial sort indicator.

        Returns:
            The widgets the dialog needs to wire up and update.
        """
        self._host = host
        self._sort_column = sort_column
        self._sort_order = sort_order

        layout = QVBoxLayout(host)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)

        main_splitter = QSplitter(Qt.Orientation.Horizontal, host)
        main_splitter.setChildrenCollapsible(False)

        left_panel = QWidget(main_splitter)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        filter_section = self._build_filter_bar(
            title=QCoreApplication.translate("LineSelectionDialog", "Filter Criteria")
        )
        left_layout.addWidget(filter_section.panel)
        results_section = self._build_results_group()
        left_layout.addWidget(results_section.group, stretch=1)
        main_splitter.addWidget(left_panel)

        right_panel = QWidget(main_splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 0, 12, 0)
        right_layout.setSpacing(12)

        right_splitter = QSplitter(Qt.Orientation.Vertical, right_panel)
        right_splitter.setChildrenCollapsible(False)
        detail_section = self._build_detail_group()
        right_splitter.addWidget(detail_section.group)
        selection_section = self._build_selection_group()
        right_splitter.addWidget(selection_section.group)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 2)
        right_layout.addWidget(right_splitter)

        main_splitter.addWidget(right_panel)
        main_splitter.setStretchFactor(0, 5)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setSizes([600, 380])

        layout.addWidget(main_splitter, stretch=1)

        button_box = self._build_button_box(ok_initially_enabled=ok_initially_enabled)
        footer = QWidget(host)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(0)
        footer_layout.addWidget(button_box)
        layout.addWidget(footer)

        return LineSelectionWidgets(
            keyword_edit=filter_section.keyword_edit,
            element_combo=filter_section.element_combo,
            stage_combo=filter_section.stage_combo,
            wavelength_min=filter_section.wavelength_min,
            wavelength_max=filter_section.wavelength_max,
            filter_warning=filter_section.filter_warning,
            clear_filters_button=filter_section.clear_filters_button,
            result_label=results_section.result_label,
            result_helper_label=results_section.result_helper_label,
            table=results_section.table,
            preview=detail_section.preview,
            selection_label=selection_section.selection_label,
            selection_list=selection_section.selection_list,
            selection_placeholder=selection_section.selection_placeholder,
            selection_stack=selection_section.selection_stack,
            remove_selection_button=selection_section.remove_selection_button,
            clear_selection_button=selection_section.clear_selection_button,
            button_box=button_box,
        )

    def _build_filter_bar(self, *, title: str) -> _FilterSection:
        host = self._host
        panel = QGroupBox(title, host)
        panel_layout = QGridLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setHorizontalSpacing(12)
        panel_layout.setVerticalSpacing(12)

        frame_width = host.style().pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, None, host)
        font_height = host.fontMetrics().height()
        field_height = max(32, font_height + frame_width * 4)

        keyword_label = QLabel(QCoreApplication.translate("LineSelectionDialog", "Keyword"), panel)
        keyword_edit = QLineEdit(panel)
        keyword_edit.setObjectName("filterKeywordEdit")
        keyword_edit.setPlaceholderText(
            QCoreApplication.translate(
                "LineSelectionDialog", "Search lines by name, multiplet, or comment"
            )
        )
        keyword_edit.setClearButtonEnabled(True)
        keyword_edit.setMinimumHeight(field_height)

        element_label = QLabel(QCoreApplication.translate("LineSelectionDialog", "Element"), panel)
        element_combo = QComboBox(panel)
        element_combo.setObjectName("filterElementCombo")
        element_combo.setEditable(True)
        element_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        element_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        element_combo.setMinimumContentsLength(4)
        element_combo.setMinimumHeight(field_height)
        element_edit = element_combo.lineEdit()
        if element_edit is None:
            msg = "Editable element combo must expose a line edit"
            raise RuntimeError(msg)
        element_edit.setClearButtonEnabled(True)
        element_edit.setPlaceholderText(
            QCoreApplication.translate("LineSelectionDialog", "All elements")
        )
        completer = element_combo.completer()
        if completer is None:
            msg = "Editable element combo must expose a completer"
            raise RuntimeError(msg)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        stage_label = QLabel(QCoreApplication.translate("LineSelectionDialog", "Ion stage"), panel)
        stage_combo = QComboBox(panel)
        stage_combo.setObjectName("filterStageCombo")
        stage_combo.setEditable(False)
        stage_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        stage_combo.setMinimumContentsLength(4)
        stage_combo.setMinimumHeight(field_height)

        wavelength_label = QLabel(
            QCoreApplication.translate("LineSelectionDialog", "Wavelength Range (Å)"), panel
        )
        range_container = QWidget(panel)
        range_container.setObjectName("filterWavelengthRange")
        range_layout = QHBoxLayout(range_container)
        range_layout.setContentsMargins(0, 0, 0, 0)
        range_layout.setSpacing(8)

        separator_label = QLabel(
            QCoreApplication.translate("LineSelectionDialog", "–"), range_container
        )
        separator_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        wavelength_min = QLineEdit(range_container)
        wavelength_min.setObjectName("filterWavelengthMin")
        min_validator = _CorrectableDoubleValidator(0.0, 50000.0, 3, wavelength_min)
        min_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        wavelength_min.setValidator(min_validator)
        wavelength_min.setPlaceholderText(
            QCoreApplication.translate("LineSelectionDialog", "No minimum")
        )
        wavelength_min.setAlignment(Qt.AlignmentFlag.AlignRight)
        wavelength_min.setClearButtonEnabled(True)
        wavelength_min.setMinimumHeight(field_height)
        wavelength_min.setFixedWidth(150)

        wavelength_max = QLineEdit(range_container)
        wavelength_max.setObjectName("filterWavelengthMax")
        max_validator = _CorrectableDoubleValidator(0.0, 50000.0, 3, wavelength_max)
        max_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        wavelength_max.setValidator(max_validator)
        wavelength_max.setPlaceholderText(
            QCoreApplication.translate("LineSelectionDialog", "No maximum")
        )
        wavelength_max.setAlignment(Qt.AlignmentFlag.AlignRight)
        wavelength_max.setClearButtonEnabled(True)
        wavelength_max.setMinimumHeight(field_height)
        wavelength_max.setFixedWidth(150)

        unit_label = QLabel("Å", range_container)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        range_layout.addWidget(wavelength_min)
        range_layout.addWidget(separator_label)
        range_layout.addWidget(wavelength_max)
        range_layout.addWidget(unit_label)
        range_layout.addStretch(1)

        element_label.setBuddy(element_combo)
        stage_label.setBuddy(stage_combo)
        wavelength_label.setBuddy(wavelength_min)
        element_combo.setAccessibleName(
            QCoreApplication.translate("LineSelectionDialog", "Element filter")
        )
        wavelength_min.setAccessibleName(
            QCoreApplication.translate("LineSelectionDialog", "Minimum wavelength")
        )
        wavelength_max.setAccessibleName(
            QCoreApplication.translate("LineSelectionDialog", "Maximum wavelength")
        )

        filter_warning = QLabel(panel)
        filter_warning.setObjectName("filterWarningLabel")
        filter_warning.setStyleSheet(f"color: {Colors.ERROR}; font-weight: 500;")
        filter_warning.hide()

        button_container = QWidget(panel)
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)

        clear_filters_button = QPushButton(
            QCoreApplication.translate("LineSelectionDialog", "Clear filters"), panel
        )
        clear_filters_button.setObjectName("clearFiltersButton")
        clear_filters_button.setMinimumHeight(field_height)
        apply_button_variant(clear_filters_button, "secondary")
        apply_action_row_sizing(clear_filters_button)
        button_layout.addStretch()
        button_layout.addWidget(clear_filters_button)

        panel_layout.addWidget(keyword_label, 0, 0)
        panel_layout.addWidget(keyword_edit, 0, 1, 1, 3)
        panel_layout.addWidget(element_label, 1, 0)
        panel_layout.addWidget(element_combo, 1, 1)
        panel_layout.addWidget(stage_label, 1, 2)
        panel_layout.addWidget(stage_combo, 1, 3)
        panel_layout.addWidget(wavelength_label, 2, 0)
        panel_layout.addWidget(range_container, 2, 1, 1, 3)
        panel_layout.addWidget(filter_warning, 3, 0, 1, 4)
        panel_layout.addWidget(button_container, 4, 0, 1, 4, Qt.AlignmentFlag.AlignRight)

        panel_layout.setColumnStretch(1, 1)
        panel_layout.setColumnStretch(3, 1)

        return _FilterSection(
            panel=panel,
            keyword_edit=keyword_edit,
            element_combo=element_combo,
            stage_combo=stage_combo,
            wavelength_min=wavelength_min,
            wavelength_max=wavelength_max,
            filter_warning=filter_warning,
            clear_filters_button=clear_filters_button,
        )

    def _build_result_summary(self) -> tuple[QWidget, QLabel]:
        container = QWidget(self._host)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        #: {count} is the number of result lines; translators must keep the placeholder.
        result_count_template = QCoreApplication.translate("LineSelectionDialog", "{count} lines")
        result_label = QLabel(result_count_template.format(count=0), container)
        result_label.setObjectName("resultSummaryLabel")
        layout.addWidget(result_label)
        layout.addStretch()

        return container, result_label

    def _build_results_group(self) -> _ResultsSection:
        group = QGroupBox(QCoreApplication.translate("LineSelectionDialog", "Results"), self._host)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        summary_container, result_label = self._build_result_summary()
        layout.addWidget(summary_container)
        table = self._build_results_table()
        layout.addWidget(table, stretch=1)

        result_helper_label = QLabel(
            QCoreApplication.translate(
                "LineSelectionDialog", "Double-click to add immediately / Space toggles selection"
            ),
            group,
        )
        result_helper_label.setObjectName("resultHelperLabel")
        result_helper_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(result_helper_label)

        return _ResultsSection(
            group=group,
            table=table,
            result_label=result_label,
            result_helper_label=result_helper_label,
        )

    def _build_results_table(self) -> QTableWidget:
        table = QTableWidget(self._host)
        table.setObjectName("lineResultTable")
        table.setColumnCount(5)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(1, 5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(48)
        header.setSortIndicator(self._sort_column, self._sort_order)
        table.setSortingEnabled(True)
        return table

    def _build_detail_group(self) -> _DetailSection:
        group = QGroupBox(
            QCoreApplication.translate("LineSelectionDialog", "Line Details"), self._host
        )
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        detail_panel, preview = self._build_detail_panel()
        layout.addWidget(detail_panel, stretch=1)

        return _DetailSection(group=group, preview=preview)

    def _build_detail_panel(self) -> tuple[QWidget, QTextEdit]:
        panel = QWidget(self._host)
        panel.setMinimumWidth(300)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(12)

        preview = QTextEdit(panel)
        preview.setReadOnly(True)
        preview.setObjectName("linePreview")
        preview.setPlaceholderText(
            QCoreApplication.translate(
                "LineSelectionDialog", "Select a line in the table to view details."
            )
        )
        preview.setMinimumHeight(140)
        layout.addWidget(preview, stretch=1)

        return panel, preview

    def _build_selection_group(self) -> _SelectionSection:
        group = QGroupBox(
            QCoreApplication.translate("LineSelectionDialog", "Lines to Add"), self._host
        )
        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        selection_count_template = QCoreApplication.translate(
            "LineSelectionDialog", "{count} lines"
        )
        selection_label = QLabel(selection_count_template.format(count=0), group)
        selection_label.setObjectName("selectionSummaryLabel")
        layout.addWidget(selection_label)

        list_container = QWidget(group)
        list_container.setObjectName("selectionListContainer")
        selection_stack = QStackedLayout(list_container)
        selection_stack.setContentsMargins(0, 0, 0, 0)

        selection_placeholder = QLabel(
            QCoreApplication.translate("LineSelectionDialog", "No lines selected yet."),
            list_container,
        )
        selection_placeholder.setObjectName("selectionPlaceholderLabel")
        selection_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selection_placeholder.setStyleSheet(empty_state_label_style())
        selection_placeholder.setWordWrap(True)
        selection_stack.addWidget(selection_placeholder)

        selection_list = QListWidget(list_container)
        selection_list.setObjectName("selectionList")
        selection_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        selection_list.setMinimumHeight(160)
        selection_stack.addWidget(selection_list)
        selection_stack.setCurrentWidget(selection_placeholder)

        layout.addWidget(list_container, stretch=1)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)
        button_row.addStretch()

        remove_selection_button = QPushButton(
            QCoreApplication.translate("LineSelectionDialog", "Remove selection"), group
        )
        remove_selection_button.setObjectName("selectionRemoveButton")
        apply_button_variant(remove_selection_button, "secondary")
        button_row.addWidget(remove_selection_button)

        clear_selection_button = QPushButton(
            QCoreApplication.translate("LineSelectionDialog", "Clear selection"), group
        )
        clear_selection_button.setObjectName("selectionClearButton")
        apply_button_variant(clear_selection_button, "secondary")
        button_row.addWidget(clear_selection_button)
        apply_action_row_sizing(remove_selection_button, clear_selection_button)
        layout.addLayout(button_row)

        return _SelectionSection(
            group=group,
            selection_label=selection_label,
            selection_list=selection_list,
            selection_placeholder=selection_placeholder,
            selection_stack=selection_stack,
            remove_selection_button=remove_selection_button,
            clear_selection_button=clear_selection_button,
        )

    def _build_button_box(self, *, ok_initially_enabled: bool) -> QDialogButtonBox:
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok,
            Qt.Orientation.Horizontal,
            self._host,
        )
        ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if isinstance(ok_button, QPushButton):
            ok_button.setObjectName("lineSelectionApplyButton")
            ok_button.setText(
                QCoreApplication.translate("LineSelectionDialog", "Add selected lines")
            )
            ok_button.setEnabled(ok_initially_enabled)
            apply_button_variant(ok_button, "primary")

        cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if isinstance(cancel_button, QPushButton):
            cancel_button.setObjectName("lineSelectionCancelButton")
            cancel_button.setText(QCoreApplication.translate("LineSelectionDialog", "Cancel"))
            apply_button_variant(cancel_button, "secondary")

        return button_box
