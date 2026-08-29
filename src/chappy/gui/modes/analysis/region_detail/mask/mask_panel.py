"""Mask management panel for optimize mode."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, ClassVar, cast, overload

from PySide6.QtCore import QEvent, QModelIndex, QPersistentModelIndex, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.common.disclosure_header import DisclosureHeaderButton
from chappy.gui.theme import apply_button_variant
from chappy.i18n import get_language_switcher

MIN_MASK_WIDTH = 0.01

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.core.masking import MaskDefinition


def _model_index_from_qt_index(index: QModelIndex | QPersistentModelIndex) -> QModelIndex:
    """Return a concrete QModelIndex for Qt APIs that reject persistent stubs."""
    if isinstance(index, QPersistentModelIndex):
        return cast("QModelIndex", index)
    return index


@dataclass(slots=True)
class _MaskRow:
    identifier: str
    label: str
    start: float
    end: float
    width: float


class _MaskTreeWidget(QTreeWidget):
    """Tree widget that limits editing to start/end columns."""

    _editable_columns: ClassVar[set[int]] = {1, 2}

    @overload
    def edit(self, index: QModelIndex | QPersistentModelIndex, /) -> None: ...

    @overload
    def edit(
        self,
        index: QModelIndex | QPersistentModelIndex,
        trigger: QAbstractItemView.EditTrigger,
        event: QEvent,
        /,
    ) -> bool: ...

    def edit(
        self,
        index: QModelIndex | QPersistentModelIndex,
        trigger: QAbstractItemView.EditTrigger | None = None,
        event: QEvent | None = None,
    ) -> bool | None:
        model_index = _model_index_from_qt_index(index)
        if model_index.column() not in self._editable_columns:
            return False
        if trigger is None and event is None:
            return super().edit(model_index)
        if trigger is None:
            trigger = QAbstractItemView.EditTrigger.CurrentChanged
        if event is None:
            event = QEvent(QEvent.Type.None_)
        return super().edit(model_index, trigger, event)


class OptimizeMaskPanel(QFrame):
    """List panel showing configured wavelength masks."""

    add_mask_requested = Signal()
    edit_mask_requested = Signal(str)
    mask_selected = Signal(str)
    remove_mask_requested = Signal(str)
    mask_range_changed = Signal(str, float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("optimizeMaskPanel")
        self._language_switcher = get_language_switcher(self)

        self._rows: dict[str, _MaskRow] = {}
        self._is_collapsed = True
        self._user_override = False
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._header_button = DisclosureHeaderButton(
            self, object_name="maskCollapseToggle", title_object_name="maskTitleLabel"
        )
        self._header_button.setChecked(False)
        self._header_button.toggled.connect(self._on_collapse_toggled)
        layout.addWidget(self._header_button)

        self._content_widget = QWidget(self)
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(6)

        self._add_button = QPushButton(self.tr("Add Masked Range"))
        self._add_button.setObjectName("maskAddButton")
        self._add_button.setCheckable(True)
        self._add_button.setChecked(False)
        self._add_button.clicked.connect(self.add_mask_requested.emit)
        apply_button_variant(self._add_button, "primary")
        add_row.addWidget(self._add_button)
        add_row.addStretch(1)

        content_layout.addLayout(add_row)

        self._tree = _MaskTreeWidget(self._content_widget)
        self._tree.setColumnCount(5)
        self._tree.setHeaderLabels(self._header_labels())
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setUniformRowHeights(True)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        content_layout.addWidget(self._tree, stretch=1)

        layout.addWidget(self._content_widget, stretch=1)

        if self._language_switcher is not None:
            self._language_switcher.language_changed.connect(self._on_language_changed)

        self.retranslate_ui()

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.set_collapsed(True)

    def set_masks(self, masks: Iterable[MaskDefinition]) -> None:
        """Populate tree with mask definitions."""
        self._rows.clear()
        self._syncing = True
        self._tree.blockSignals(True)
        self._tree.clear()

        for mask in masks:
            row = _MaskRow(
                identifier=mask.identifier,
                label=mask.label or self._fallback_label(mask),
                start=mask.wavelength_min,
                end=mask.wavelength_max,
                width=mask.full_width,
            )
            self._rows[row.identifier] = row

            item = QTreeWidgetItem(
                [row.label, f"{row.start:.2f}", f"{row.end:.2f}", f"{row.width:.2f}", ""]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, row.identifier)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
            if not mask.enabled:
                for col in range(5):
                    item.setForeground(col, Qt.GlobalColor.darkGray)
            self._tree.addTopLevelItem(item)

            delete_button = self._create_delete_button(row.identifier)
            self._tree.setItemWidget(item, 4, delete_button)

        self._tree.sortItems(1, Qt.SortOrder.AscendingOrder)

        if not self._rows:
            self.set_collapsed(True)
        elif not self._user_override:
            self.set_collapsed(False)

        self._tree.blockSignals(False)
        self._syncing = False

    def select_mask(self, mask_id: str | None) -> None:
        """Select mask row by identifier."""
        if mask_id is None:
            self._tree.clearSelection()
            return
        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item is None:
                continue
            identifier = item.data(0, Qt.ItemDataRole.UserRole)
            if identifier == mask_id:
                self._tree.setCurrentItem(item)
                return

    def set_add_button_active(self, active: bool) -> None:
        """Toggle the add mask button state.

        Args:
            active: Whether the add button should appear pressed and disabled.
        """
        self._add_button.setChecked(active)
        self._add_button.setDown(active)
        self._add_button.setEnabled(not active)

    def clear_add_button_focus(self) -> None:
        """Remove keyboard focus from the add mask button."""
        self._add_button.clearFocus()

    def set_add_button_enabled(self, enabled: bool) -> None:
        """Enable or disable the add mask button when idle.

        Args:
            enabled: Whether the add button should be interactable.
        """
        if self._add_button.isChecked():
            return
        self._add_button.setEnabled(enabled)

    def set_collapsed(self, collapsed: bool) -> None:
        """Collapse or expand the mask panel contents.

        Args:
            collapsed: Whether the panel contents should be hidden.
        """
        if self._is_collapsed == collapsed and self._content_widget.isHidden() == collapsed:
            return
        self._is_collapsed = collapsed
        with QSignalBlocker(self._header_button):
            self._header_button.setChecked(not collapsed)
        self._apply_collapse_state()

    def expand(self) -> None:
        """Ensure the mask panel is expanded."""
        self.set_collapsed(False)

    def retranslate_ui(self) -> None:
        """Update visible strings to match the active language."""
        self._header_button.set_title(self.tr("Masked Ranges"))
        self._add_button.setText(self.tr("Add Masked Range"))
        self._tree.setHeaderLabels(self._header_labels())
        self._update_delete_button_labels()

    def _header_labels(self) -> list[str]:
        """Return the translated column headers."""
        return [
            self.tr("Name"),
            self.tr("Start (Å)"),
            self.tr("End (Å)"),
            self.tr("Width (Å)"),
            self.tr("Actions"),
        ]

    def _update_delete_button_labels(self) -> None:
        """Refresh delete button accessibility labels."""
        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item is None:
                continue
            widget = self._tree.itemWidget(item, 4)
            if isinstance(widget, QToolButton):
                widget.setToolTip(self.tr("Delete this masked range"))
                widget.setAccessibleName(self.tr("Delete Masked Range"))

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._syncing:
            return
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(identifier, str):
            return
        row = self._rows.get(identifier)
        if row is None:
            return
        if column not in (1, 2):
            self._restore_row_text(item, row)
            return

        text = item.text(column).strip()
        try:
            value = float(text)
        except ValueError:
            self._restore_row_text(item, row)
            return

        new_start = row.start
        new_end = row.end
        if column == 1:
            new_start = value
        else:
            new_end = value

        if new_end < new_start:
            new_start, new_end = new_end, new_start

        if new_end - new_start < MIN_MASK_WIDTH:
            if column == 1:
                new_end = new_start + MIN_MASK_WIDTH
            else:
                new_start = new_end - MIN_MASK_WIDTH

        if new_start == row.start and new_end == row.end:
            self._restore_row_text(item, row)
            return

        new_start = round(new_start, 2)
        new_end = round(new_end, 2)
        if new_end < new_start:
            new_start, new_end = new_end, new_start
        if new_end - new_start < MIN_MASK_WIDTH:
            new_end = round(new_start + MIN_MASK_WIDTH, 2)
        row.start = new_start
        row.end = new_end
        row.width = round(abs(new_end - new_start), 2)

        self._syncing = True
        self._tree.blockSignals(True)
        item.setText(1, f"{row.start:.2f}")
        item.setText(2, f"{row.end:.2f}")
        item.setText(3, f"{row.width:.2f}")
        self._tree.blockSignals(False)
        self._syncing = False

        self.mask_range_changed.emit(identifier, row.start, row.end)

    def _restore_row_text(self, item: QTreeWidgetItem, row: _MaskRow) -> None:
        self._syncing = True
        self._tree.blockSignals(True)
        item.setText(0, row.label)
        item.setText(1, f"{row.start:.2f}")
        item.setText(2, f"{row.end:.2f}")
        item.setText(3, f"{row.width:.2f}")
        self._tree.blockSignals(False)
        self._syncing = False

    def _on_selection_changed(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            self.mask_selected.emit(None)
            return
        item = items[0]
        if item is None:
            self.mask_selected.emit(None)
            return
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(identifier, str):
            self.mask_selected.emit(identifier)
        else:
            self.mask_selected.emit(None)

    def _on_item_double_clicked(self, item: QTreeWidgetItem) -> None:
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(identifier, str):
            self.edit_mask_requested.emit(identifier)

    def _fallback_label(self, mask: MaskDefinition) -> str:
        start, end = mask.wavelength_min, mask.wavelength_max
        return f"{start:.1f}–{end:.1f}"

    def _create_delete_button(self, mask_id: str) -> QToolButton:
        button = QToolButton(self._tree)
        button.setText("×")
        button.setToolTip(self.tr("Delete this masked range"))
        button.setAccessibleName(self.tr("Delete Masked Range"))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(True)
        button.clicked.connect(partial(self._on_delete_button_clicked, mask_id))
        return button

    def _on_language_changed(self, _code: str) -> None:
        """Handle runtime language changes triggered by the language switcher."""
        self.retranslate_ui()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Refresh translated text when Qt translators change."""
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()
        super().changeEvent(event)

    def _on_collapse_toggled(self, expanded: bool) -> None:
        self._user_override = True
        self._is_collapsed = not expanded
        self._apply_collapse_state()

    def _apply_collapse_state(self) -> None:
        expanded = not self._is_collapsed
        self._header_button.set_chevron_expanded(expanded)
        self._content_widget.setVisible(expanded)

    def _on_delete_button_clicked(self, mask_id: str) -> None:
        self.remove_mask_requested.emit(mask_id)
