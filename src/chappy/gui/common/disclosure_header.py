"""Accessible full-width disclosure header for side-panel sections."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QStyle, QToolButton, QWidget

from chappy.gui.common.side_panel_heading import apply_side_panel_heading_style
from chappy.gui.theme import Colors
from chappy.gui.visual_tokens import SidePanelMetrics

if TYPE_CHECKING:
    from PySide6.QtGui import QFocusEvent, QKeyEvent, QPaintEvent, QResizeEvent


class _ElidedSummaryLabel(QLabel):
    """Summary label that elides instead of enlarging its parent panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""

    @property
    def full_text(self) -> str:
        """Return the complete, unelided summary text."""
        return self._full_text

    def set_full_text(self, text: str) -> None:
        """Store the complete summary and render it within the current width."""
        self._full_text = text
        self.setToolTip(text)
        self._apply_elide()

    @override
    def minimumSizeHint(self) -> QSize:
        """Report zero width so the summary never blocks panel shrinking."""
        return QSize(0, super().minimumSizeHint().height())

    @override
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Re-elide the summary whenever the available width changes."""
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        elided = self.fontMetrics().elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, max(0, self.width())
        )
        self.setText(elided)


class DisclosureHeaderButton(QToolButton):
    """Single focusable header with a title, summary, and trailing chevron."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        object_name: str,
        title_object_name: str | None = None,
    ) -> None:
        """Create a full-width disclosure button.

        Args:
            parent: Owning widget.
            object_name: Stable object name for the interactive header.
            title_object_name: Optional object name for the embedded title label.
        """
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setCheckable(True)
        self.setChecked(True)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._title_label = QLabel(self)
        if title_object_name is not None:
            self._title_label.setObjectName(title_object_name)
        self._title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        apply_side_panel_heading_style(self._title_label)

        self.summary_label = _ElidedSummaryLabel(self)
        self.summary_label.setObjectName("disclosureHeaderSummary")
        self.summary_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.summary_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        self.summary_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self._arrow_label = QLabel(self)
        self._arrow_label.setObjectName("disclosureHeaderChevron")
        self._arrow_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._header_layout = QHBoxLayout(self)
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(SidePanelMetrics.COLLAPSIBLE_HEADER_SPACING)
        self._header_layout.addWidget(self._title_label)
        self._header_layout.addWidget(self.summary_label, 1)
        self._header_layout.addWidget(self._arrow_label)
        self._arrow_type = Qt.ArrowType.DownArrow
        self._keyboard_focus_visible = False
        self.setStyleSheet(
            f"QToolButton#{object_name} {{ border: none; background: transparent; padding: 0; }}"
            f"QToolButton#{object_name}:hover {{ background: {Colors.UI_ACCENT_MUTED}; }}"
        )
        self._refresh_arrow()

    @property
    def title_label(self) -> QLabel:
        """Return the embedded title label for annotation and geometry inspection."""
        return self._title_label

    def set_title(self, title: str) -> None:
        """Set the visible and accessible title of the disclosure button."""
        self.setAccessibleName(title)
        self._title_label.setText(title)
        self.updateGeometry()

    def set_summary(self, summary: str) -> None:
        """Set the elided summary and expose its full value as a tooltip."""
        self.summary_label.set_full_text(summary)
        self.setToolTip(summary)

    def set_chevron_expanded(self, expanded: bool) -> None:
        """Render the trailing chevron for the actual content visibility."""
        arrow_type = Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        if arrow_type == self._arrow_type:
            return
        self._arrow_type = arrow_type
        self._refresh_arrow()

    @override
    def sizeHint(self) -> QSize:
        """Include child labels because QToolButton ignores its child layout."""
        layout_hint = self._header_layout.sizeHint()
        base_hint = super().sizeHint()
        return QSize(max(layout_hint.width(), base_hint.width()), max(layout_hint.height(), 24))

    @override
    def minimumSizeHint(self) -> QSize:
        """Allow the summary to elide while preserving the title and chevron."""
        layout_hint = self._header_layout.minimumSize()
        return QSize(layout_hint.width(), max(layout_hint.height(), 24))

    @override
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Activate with Enter in addition to QAbstractButton's Space handling."""
        self._keyboard_focus_visible = True
        self.update()
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)

    @override
    def focusInEvent(self, event: QFocusEvent) -> None:
        """Show a focus outline only when focus arrived through the keyboard."""
        self._keyboard_focus_visible = event.reason() in (
            Qt.FocusReason.TabFocusReason,
            Qt.FocusReason.BacktabFocusReason,
            Qt.FocusReason.ShortcutFocusReason,
        )
        super().focusInEvent(event)
        self.update()

    @override
    def focusOutEvent(self, event: QFocusEvent) -> None:
        """Clear the keyboard-only focus outline when focus leaves the header."""
        self._keyboard_focus_visible = False
        super().focusOutEvent(event)
        self.update()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the keyboard focus outline without shifting aligned labels."""
        super().paintEvent(event)
        if not self._keyboard_focus_visible:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(Colors.BORDER_FOCUS), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    @override
    def changeEvent(self, event: QEvent) -> None:
        """Refresh the native chevron after palette or style changes."""
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.EnabledChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
        ):
            self._refresh_arrow()

    def _refresh_arrow(self) -> None:
        standard_pixmap = (
            QStyle.StandardPixmap.SP_ArrowDown
            if self._arrow_type == Qt.ArrowType.DownArrow
            else QStyle.StandardPixmap.SP_ArrowRight
        )
        icon = self.style().standardIcon(standard_pixmap, None, self)
        extent = self.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize, None, self)
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self._arrow_label.setFixedSize(extent, extent)
        self._arrow_label.setPixmap(icon.pixmap(QSize(extent, extent), mode))
