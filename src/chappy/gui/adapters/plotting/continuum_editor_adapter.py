"""Qt adapters for Matplotlib continuum editor UI behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QMenu, QToolTip, QWidget

from chappy.plotting.components.continuum_editor import (
    ContinuumContextState,
    ContinuumCursorShape,
    MatplotlibContinuumEditor,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


class QtContinuumEditorUiAdapter:
    """Qt-owned cursor, tooltip, and context menu adapter for continuum editing."""

    def __init__(self, canvas: object) -> None:
        """Initialize the adapter.

        Args:
            canvas: Matplotlib canvas that must also be a QWidget.
        """
        if not isinstance(canvas, QWidget):
            msg = "QtContinuumEditorUiAdapter requires a QWidget canvas."
            raise TypeError(msg)
        self._canvas = canvas

    def set_cursor(self, cursor: ContinuumCursorShape) -> None:
        """Set the canvas cursor."""
        self._canvas.setCursor(self._to_qt_cursor(cursor))

    def show_coordinate_tooltip(self, text: str) -> None:
        """Show a tooltip at the current cursor position."""
        QToolTip.showText(QCursor.pos(), text, self._canvas)

    def clear_tooltip(self) -> None:
        """Hide the active tooltip."""
        QToolTip.hideText()

    def open_context_menu(
        self,
        *,
        context_state: ContinuumContextState | None,
        add_label: str,
        delete_label: str,
        request_add: Callable[[float, float], bool],
        request_delete: Callable[[int], bool],
    ) -> None:
        """Open the continuum context menu and dispatch selected actions."""
        menu = QMenu(self._canvas)

        add_action = menu.addAction(add_label)
        add_action.setEnabled(bool(context_state and context_state.can_add))

        delete_action = menu.addAction(delete_label)
        delete_action.setEnabled(
            bool(
                context_state
                and context_state.can_delete
                and context_state.nearest_index is not None
            )
        )

        chosen = menu.exec(QCursor.pos())

        if chosen == add_action and context_state and context_state.can_add:
            flux = context_state.flux
            if flux is not None:
                request_add(context_state.wavelength, flux)
        elif (
            chosen == delete_action
            and context_state
            and context_state.nearest_index is not None
            and context_state.can_delete
        ):
            request_delete(context_state.nearest_index)

    @staticmethod
    def _to_qt_cursor(cursor: ContinuumCursorShape) -> Qt.CursorShape:
        """Map continuum cursor tokens to Qt cursor shapes."""
        if cursor == "pointing_hand":
            return Qt.CursorShape.PointingHandCursor
        if cursor == "closed_hand":
            return Qt.CursorShape.ClosedHandCursor
        if cursor == "forbidden":
            return Qt.CursorShape.ForbiddenCursor
        return Qt.CursorShape.ArrowCursor


def schedule_qt_timer(milliseconds: int, callback: Callable[[], None]) -> None:
    """Schedule a callback using Qt timer ownership."""
    QTimer.singleShot(milliseconds, callback)


def create_matplotlib_continuum_editor_adapter(
    *, axes: Axes, figure: Figure, translate: Callable[[str], str]
) -> MatplotlibContinuumEditor:
    """Create a Matplotlib continuum editor with Qt-owned UI behaviours."""
    return MatplotlibContinuumEditor(
        axes,
        figure,
        ui_port=QtContinuumEditorUiAdapter(figure.canvas),
        feedback_scheduler=schedule_qt_timer,
        translate=translate,
    )
