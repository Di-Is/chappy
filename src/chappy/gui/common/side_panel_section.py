"""Card-framed side-panel section shared across every editing-mode panel."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from chappy.gui.common.side_panel_heading import apply_side_panel_heading_style
from chappy.gui.theme import card_frame_style
from chappy.gui.visual_tokens import SidePanelMetrics


class SidePanelSection(QFrame):
    """Bordered side-panel section with a peer-styled heading.

    Every mode groups its side-panel controls with this card so the identify,
    continuum, and analysis panels read as siblings.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        object_name: str,
        title: str | None = None,
        spacing: int = SidePanelMetrics.SECTION_SPACING,
    ) -> None:
        """Frame the section and reserve a heading slot when ``title`` is given."""
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setStyleSheet(card_frame_style(object_name))

        self._body = QVBoxLayout(self)
        self._body.setContentsMargins(*SidePanelMetrics.CARD_CONTENT_MARGIN)
        self._body.setSpacing(spacing)

        self._title_label: QLabel | None = None
        if title is not None:
            self.ensure_heading().setText(title)

    @property
    def body(self) -> QVBoxLayout:
        """Return the content layout so callers append their controls."""
        return self._body

    @property
    def title_label(self) -> QLabel | None:
        """Return the heading label, or ``None`` when the section has no title."""
        return self._title_label

    def ensure_heading(self) -> QLabel:
        """Return the heading label, creating the heading slot on first use."""
        if self._title_label is None:
            self._title_label = QLabel(self)
            apply_side_panel_heading_style(self._title_label)
            self._body.insertWidget(0, self._title_label)
        return self._title_label

    def set_title(self, text: str) -> None:
        """Set the heading text, creating the heading slot on first use."""
        self.ensure_heading().setText(text)
