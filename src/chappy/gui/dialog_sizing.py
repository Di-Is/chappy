"""Layout-derived sizing for widgets with translated labels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QPushButton

if TYPE_CHECKING:
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QLayout, QWidget

_INITIAL_SIZE_APPLIED_PROPERTY = "chappyInitialSizeApplied"


def _activated_layout(widget: QWidget) -> QLayout | None:
    """Return the widget layout, recalculated with label-derived button widths."""
    layout = widget.layout()
    if layout is None:
        return None
    # The app stylesheet's QPushButton min-width makes QStyleSheetStyle report
    # button minimums independent of label length, so pin each button to its
    # label-derived size hint before measuring the layout.
    for button in widget.findChildren(QPushButton):
        button.setMinimumWidth(button.sizeHint().width())
    layout.activate()
    return layout


def enforce_translated_minimum_size(
    widget: QWidget, *, floor: QSize, initial: QSize | None = None
) -> None:
    """Raise the widget minimum to fit the current language's labels.

    Call after applying translations (and again on every runtime language
    switch) so the minimum tracks the rendered label widths. Width-dependent
    heights (word-wrapped labels) are evaluated at the computed minimum width
    so fixed-height rows below them are not squeezed out. The current size
    is never shrunk; Qt clamps it automatically when it falls below the new
    minimum. When ``initial`` is given, the first call also resizes the widget
    to ``initial`` expanded to the computed minimum.
    """
    layout = _activated_layout(widget)
    if layout is None:
        return
    layout_minimum = layout.minimumSize()
    minimum_width = max(floor.width(), layout_minimum.width())
    minimum_height = max(floor.height(), layout_minimum.height())
    if layout.hasHeightForWidth():
        minimum_height = max(minimum_height, layout.minimumHeightForWidth(minimum_width))
    widget.setMinimumSize(minimum_width, minimum_height)
    if initial is not None and not widget.property(_INITIAL_SIZE_APPLIED_PROPERTY):
        widget.setProperty(_INITIAL_SIZE_APPLIED_PROPERTY, True)
        widget.resize(max(initial.width(), minimum_width), max(initial.height(), minimum_height))


def fit_height_to_width(widget: QWidget) -> None:
    """Give a fixed-width widget the height its labels need at that width.

    ``QWidget.adjustSize`` applies heightForWidth to windows only, so a
    non-window panel that cannot widen must evaluate it explicitly; otherwise
    its word-wrapped labels are squeezed below their wrapped height and their
    tails disappear.
    """
    layout = _activated_layout(widget)
    if layout is None:
        return
    height = layout.totalMinimumSize().height()
    if layout.hasHeightForWidth():
        height = max(height, layout.totalMinimumHeightForWidth(widget.width()))
    widget.setFixedHeight(height)


__all__ = ["enforce_translated_minimum_size", "fit_height_to_width"]
