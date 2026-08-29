"""Collapsible section widget with a peer-aligned disclosure header.

Shared by the Identify and Analysis side panels so every mode keeps the
same section grammar.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from chappy.gui.common.disclosure_header import DisclosureHeaderButton
from chappy.gui.visual_tokens import SidePanelMetrics


class CollapsibleSection(QWidget):
    """Section widget whose content can be collapsed behind a summary header."""

    collapse_toggled = Signal(bool)

    def __init__(
        self,
        content: QWidget,
        parent: QWidget | None = None,
        *,
        header_object_name: str,
        expanded_vertical_policy: QSizePolicy.Policy = QSizePolicy.Policy.Maximum,
    ) -> None:
        """Wrap ``content`` with a clickable collapse header."""
        super().__init__(parent)
        self._content = content
        self._expanded_vertical_policy = expanded_vertical_policy

        self._header_button = DisclosureHeaderButton(self, object_name=header_object_name)
        self._header_button.toggled.connect(self._on_header_toggled)
        self._summary_label = self._header_button.summary_label

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SidePanelMetrics.COLLAPSIBLE_HEADER_SPACING)
        layout.addWidget(self._header_button)
        content.setParent(self)
        layout.addWidget(content)

        self._sync_content_visibility()

    def set_title(self, title: str) -> None:
        """Set the header title text."""
        self._header_button.set_title(title)

    def set_summary(self, summary: str) -> None:
        """Set the summary text displayed next to the title."""
        self._header_button.set_summary(summary)

    def is_collapsed(self) -> bool:
        """Return whether the content is currently hidden."""
        return not self._header_button.isChecked()

    def set_collapsed(self, collapsed: bool) -> None:
        """Collapse or expand the content."""
        self._header_button.setChecked(not collapsed)

    def _on_header_toggled(self, expanded: bool) -> None:
        self._sync_content_visibility()
        self.collapse_toggled.emit(not expanded)

    def _sync_content_visibility(self) -> None:
        expanded = self._header_button.isChecked()
        self._content.setVisible(expanded)
        self._header_button.set_chevron_expanded(expanded)
        vertical_policy = (
            self._expanded_vertical_policy if expanded else QSizePolicy.Policy.Maximum
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, vertical_policy)
        self.updateGeometry()
