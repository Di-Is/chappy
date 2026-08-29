"""Qt tree widget primitives for optimize mode."""

from __future__ import annotations

from typing import Protocol, cast, overload

from PySide6.QtCore import (
    QAbstractItemModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QDoubleValidator, QPainter, QPalette, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLineEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QWidget,
)

from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    ROLE_EDIT_KIND,
    ROLE_RAW_VALUE,
    TreeCellEditKind,
)
from chappy.gui.theme import Colors


class QtStyleOptionViewItemRuntime(Protocol):
    """Runtime attributes exposed by QStyleOptionViewItem but missing from stubs."""

    @property
    def backgroundBrush(self) -> QBrush:  # noqa: N802 - Qt runtime attribute
        """Return the Qt background brush."""
        ...

    @backgroundBrush.setter
    def backgroundBrush(self, value: QBrush) -> None:  # noqa: N802 - Qt runtime attribute
        """Set the Qt background brush."""
        ...

    palette: QPalette
    rect: QRect
    state: QStyle.StateFlag
    widget: QWidget | None


def model_index_from_qt_index(index: QModelIndex | QPersistentModelIndex) -> QModelIndex:
    """Return a concrete QModelIndex for Qt APIs that reject persistent stubs."""
    if isinstance(index, QPersistentModelIndex):
        return cast("QModelIndex", index)
    return index


def style_option_runtime(option: QStyleOptionViewItem) -> QtStyleOptionViewItemRuntime:
    """Expose runtime QStyleOptionViewItem attributes through a typed boundary."""
    return cast("QtStyleOptionViewItemRuntime", option)


class OptimizeTreeWidget(QTreeWidget):
    """Tree widget that restricts editing to specific columns."""

    viewport_resized = Signal()

    def __init__(
        self, editable_columns: set[int] | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        _ = editable_columns

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt method override
        """Announce the new viewport width so column widths can be redistributed."""
        super().resizeEvent(event)
        self.viewport_resized.emit()

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
        """Start editing only when the target column is editable."""
        model_index = model_index_from_qt_index(index)
        if tree_cell_edit_kind(model_index) is TreeCellEditKind.NONE:
            return False

        if trigger is None or event is None:
            default_trigger = (
                trigger if trigger is not None else QAbstractItemView.EditTrigger.CurrentChanged
            )
            synthetic_event = event if event is not None else QEvent(QEvent.Type.None_)
            return super().edit(model_index, default_trigger, synthetic_event)

        return super().edit(model_index, trigger, event)


class BackgroundAwareItemDelegate(QStyledItemDelegate):
    """Ensure item-specific background brushes render under the global stylesheet."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint item backgrounds from item data before drawing foreground content."""
        model_index = model_index_from_qt_index(index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, model_index)
        runtime_opt = style_option_runtime(opt)

        background_data = model_index.data(Qt.ItemDataRole.BackgroundRole)
        brush: QBrush | None = background_data if isinstance(background_data, QBrush) else None

        opt_background = runtime_opt.backgroundBrush
        if brush is None and opt_background.style() != Qt.BrushStyle.NoBrush:
            brush = opt_background

        state = runtime_opt.state
        should_fill = (
            brush is not None
            and brush.style() != Qt.BrushStyle.NoBrush
            and not bool(state & QStyle.StateFlag.State_Selected)
        )

        if should_fill:
            painter.save()
            painter.fillRect(runtime_opt.rect, brush)
            painter.restore()

            transparent = QBrush(Qt.GlobalColor.transparent)
            runtime_opt.backgroundBrush = transparent
            palette = runtime_opt.palette
            palette.setBrush(QPalette.ColorRole.Base, transparent)
            palette.setBrush(QPalette.ColorRole.AlternateBase, transparent)

        target_widget = runtime_opt.widget
        style = target_widget.style() if target_widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, target_widget)

    def createEditor(  # noqa: N802 - Qt method override
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        """Create editor with table-optimized styling.

        Args:
            parent: Parent widget for the editor.
            option: Style options for the item.
            index: Model index of the item being edited.

        Returns:
            Configured editor widget.
        """
        model_index = model_index_from_qt_index(index)
        if tree_cell_edit_kind(model_index) is TreeCellEditKind.NONE:
            return None  # type: ignore[return-value]
        editor = super().createEditor(parent, option, index)

        if isinstance(editor, QLineEdit):
            editor.setValidator(QDoubleValidator(0.0, float("inf"), 12, editor))
            # Table cell-specific compact styling to prevent visual overflow.
            editor.setStyleSheet(f"""
                QLineEdit {{
                    border: 1px solid {Colors.BORDER_FOCUS};
                    background-color: {Colors.BACKGROUND_INPUT};
                    color: {Colors.TEXT_PRIMARY};
                    padding: 2px 4px;
                    border-radius: 0px;
                }}
            """)

        return editor

    def setEditorData(  # noqa: N802 - Qt method override
        self, editor: QWidget, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        """Load the unformatted parameter value into the editor, when available.

        The display text may carry a tie-set label prefix and a rounded
        ``± error`` suffix, so editing must start from the raw value instead.
        """
        model_index = model_index_from_qt_index(index)
        raw_value = model_index.data(ROLE_RAW_VALUE)
        edit_kind = tree_cell_edit_kind(model_index)
        if isinstance(editor, QLineEdit) and isinstance(raw_value, float):
            editor.setText(repr(raw_value))
            return
        if (
            isinstance(editor, QLineEdit)
            and edit_kind is TreeCellEditKind.LINE_ANALYSIS_HALF_WIDTH
        ):
            editor.clear()
            return

        super().setEditorData(editor, index)

    def setModelData(  # noqa: N802 - Qt method override
        self,
        editor: QWidget,
        model: QAbstractItemModel,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Write the editor's plain text back through the model's edit role."""
        model_index = model_index_from_qt_index(index)
        if tree_cell_edit_kind(model_index) is TreeCellEditKind.NONE:
            return
        if isinstance(editor, QLineEdit):
            model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)
            return

        super().setModelData(editor, model, index)


def tree_cell_edit_kind(index: QModelIndex) -> TreeCellEditKind:
    """Return the typed edit contract stored on a model index."""
    raw = index.data(ROLE_EDIT_KIND)
    if isinstance(raw, TreeCellEditKind):
        return raw
    if isinstance(raw, str):
        try:
            return TreeCellEditKind(raw)
        except ValueError:
            return TreeCellEditKind.NONE
    return TreeCellEditKind.NONE
