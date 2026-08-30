"""Faithful application environment and geometry assertions for dialog tests.

Reproduces the real app rendering conditions (Fusion base style, dark palette,
application stylesheet, CJK font, installed Qt translators) so dialog sizing
tests catch label clipping that plain offscreen rendering misses.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QDialog, QWidget

from chappy.gui.application_font import configure_application_font
from chappy.gui.theme import apply_application_theme
from chappy.i18n.qt_translator import QtTranslatorInstaller


@contextmanager
def faithful_application_environment(app: QApplication, language: str) -> Iterator[None]:
    """Apply the real app theme, font, and translators; restore them on exit.

    pytest-qt shares one QApplication across the session, so every global
    mutation made here is reverted in the finally block.
    """
    previous_stylesheet = app.styleSheet()
    previous_font = QApplication.font()
    previous_palette = app.palette()
    previous_style_name = app.style().name()
    installer = QtTranslatorInstaller()
    try:
        apply_application_theme(app)
        configure_application_font(app)
        installer.install_language(language)
        yield
    finally:
        installer.remove_translators()
        app.setStyleSheet(previous_stylesheet)
        QApplication.setFont(previous_font)
        app.setPalette(previous_palette)
        app.setStyle(previous_style_name)


def _is_inside_scroll_viewport(widget: QWidget, dialog: QDialog) -> bool:
    parent = widget.parentWidget()
    while parent is not None and parent is not dialog:
        grandparent = parent.parentWidget()
        if isinstance(grandparent, QAbstractScrollArea) and parent is grandparent.viewport():
            return True
        parent = grandparent
    return False


def _clipping_ancestor_rect(child: QWidget, dialog: QDialog) -> tuple[QWidget, QRect] | None:
    child_rect = QRect(child.mapTo(dialog, QPoint(0, 0)), child.size())
    ancestor = child.parentWidget()
    while ancestor is not None:
        if ancestor is dialog:
            ancestor_rect = QRect(QPoint(0, 0), dialog.size())
        else:
            ancestor_rect = QRect(ancestor.mapTo(dialog, QPoint(0, 0)), ancestor.size())
        if not ancestor_rect.contains(child_rect):
            return ancestor, ancestor_rect
        if ancestor is dialog:
            return None
        ancestor = ancestor.parentWidget()
    return None


def assert_children_fit_at_minimum_size(dialog: QDialog) -> None:
    """Resize the dialog to its minimum and assert no visible child is clipped.

    Qt paints each widget clipped to every ancestor rect, so a child must fit
    inside its whole ancestor chain, not just the dialog rect.
    """
    dialog.resize(dialog.minimumSize())
    QApplication.processEvents()
    overflows: list[str] = []
    for child in dialog.findChildren(QWidget):
        if not child.isVisible():
            continue
        if _is_inside_scroll_viewport(child, dialog):
            continue
        clipping = _clipping_ancestor_rect(child, dialog)
        if clipping is not None:
            ancestor, ancestor_rect = clipping
            child_rect = QRect(child.mapTo(dialog, QPoint(0, 0)), child.size())
            name = child.objectName() or type(child).__name__
            ancestor_name = ancestor.objectName() or type(ancestor).__name__
            overflows.append(f"{name}: {child_rect} clipped by {ancestor_name} {ancestor_rect}")
    assert not overflows, "Widgets are clipped at the dialog minimum size:\n" + "\n".join(
        overflows
    )


__all__ = ["assert_children_fit_at_minimum_size", "faithful_application_environment"]
