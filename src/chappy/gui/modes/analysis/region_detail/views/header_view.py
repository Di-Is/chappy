"""Region Detail header: back navigation, region selector, and needs badge."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.common.side_panel_section import SidePanelSection
from chappy.gui.theme import BACK_ARROW_PREFIX, Colors, Fonts, apply_button_variant
from chappy.gui.visual_tokens import SidePanelMetrics

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from contextlib import AbstractContextManager

    from chappy.gui.modes.analysis.region_detail.group_selection_controller import (
        OptimizeGroupChoice,
    )


class RegionDetailHeaderView(QWidget):
    """Header card owning back navigation and the region selector.

    Implements ``RegionSelectorViewPort`` directly so the group selection
    controller can drive the region combo without a forwarding adapter.
    """

    back_clicked = Signal()
    group_selection_changed = Signal(int)

    def __init__(
        self, *, mode_state_available: Callable[[], bool], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._mode_state_available = mode_state_available

        self._frame = SidePanelSection(self, object_name="optimizeHeader")

        self._back_button = QPushButton(self._frame)
        self._back_button.setObjectName("analysisDetailBackButton")
        # Breadcrumb-style back affordance: compact text link, not a dominant CTA.
        apply_button_variant(self._back_button, "text")
        self._back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_button.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        )

        self._group_label = QLabel(self._frame)
        self._group_label.setObjectName("optimizeGroupLabel")

        self._group_combo = QComboBox(self._frame)
        self._group_combo.setObjectName("analysisDetailRegionSelector")
        self._group_combo.setSizePolicy(
            QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        )

        self._group_summary = QLabel(self._frame)
        self._group_summary.setObjectName("optimizeGroupSummary")
        self._group_summary.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.SIZE_SMALL};"
        )

        self._needs_badge = QLabel(self._frame)
        self._needs_badge.setObjectName("optimizeNeedsBadge")
        self._needs_badge.setVisible(False)
        self._needs_badge.setStyleSheet(
            f"padding: 2px 6px; border-radius: 8px; font-size: {Fonts.SIZE_TINY};"
            f" color: {Colors.TEXT_PRIMARY}; background-color: {Colors.WARNING};"
        )

        self._build_layout()

        self._back_button.clicked.connect(self.back_clicked.emit)
        self._group_combo.currentIndexChanged.connect(self.group_selection_changed.emit)

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        header_layout = self._frame.body
        header_layout.setSpacing(SidePanelMetrics.SECTION_SPACING // 2)

        back_row = QHBoxLayout()
        back_row.setContentsMargins(0, 0, 0, 0)
        back_row.addWidget(self._back_button)
        back_row.addStretch(1)
        header_layout.addLayout(back_row)
        header_layout.addWidget(self._group_label)
        header_layout.addWidget(self._group_combo)

        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.addWidget(self._group_summary, stretch=1)
        summary_row.addWidget(self._needs_badge)
        header_layout.addLayout(summary_row)

    def retranslate_ui(self) -> None:
        """Reapply translated text to all owned widgets."""
        self._back_button.setText(BACK_ARROW_PREFIX + self.tr("Back to Overview"))
        self._back_button.setToolTip(self.tr("Return to Analysis Overview (Alt+Left)"))
        self._group_label.setText(self.tr("Select region"))
        self._needs_badge.setText(self.tr("Needs Optimization"))

    def back_button(self) -> QPushButton:
        """Return the back-navigation button (used by tests for variant checks)."""
        return self._back_button

    def set_needs_badge_visible(self, visible: bool) -> None:
        """Set the visibility of the needs-optimization badge."""
        self._needs_badge.setVisible(visible)

    def clear_group_summary(self) -> None:
        """Clear the group summary label."""
        self._group_summary.clear()

    # -- RegionSelectorViewPort -------------------------------------------------

    def can_select_optimize_groups(self) -> bool:
        """Return whether group selection can interact with a mode state store."""
        return self._mode_state_available()

    def blocked_group_selector(self) -> AbstractContextManager[None]:
        """Return a context manager that suppresses selector change signals."""
        return self._blocked_combo()

    @contextmanager
    def _blocked_combo(self) -> Iterator[None]:
        with QSignalBlocker(self._group_combo):
            yield

    def clear_group_selector(self) -> None:
        """Clear all group selector entries."""
        self._group_combo.clear()

    def add_empty_group_choice(self) -> None:
        """Add the localized empty-group placeholder."""
        self._group_combo.addItem(self.tr("No regions"))

    def add_group_choice(self, choice: OptimizeGroupChoice) -> None:
        """Add one selectable group choice."""
        self._group_combo.addItem(choice.display_name, userData=choice.region_id)

    def set_group_selector_enabled(self, enabled: bool) -> None:
        """Set whether the group selector is enabled."""
        self._group_combo.setEnabled(enabled)

    def group_selector_count(self) -> int:
        """Return the number of selector entries."""
        return self._group_combo.count()

    def current_group_selector_index(self) -> int:
        """Return the current selector index."""
        return self._group_combo.currentIndex()

    def set_current_group_selector_index(self, index: int) -> None:
        """Set the current selector index."""
        self._group_combo.setCurrentIndex(index)

    def group_id_at_selector_index(self, index: int) -> str | None:
        """Return the group id stored at a selector index."""
        data = self._group_combo.itemData(index)
        return data if isinstance(data, str) else None

    def current_group_id_from_selector(self) -> str | None:
        """Return the currently selected group id from the selector."""
        index = self._group_combo.currentIndex()
        if index < 0:
            return None
        return self.group_id_at_selector_index(index)
