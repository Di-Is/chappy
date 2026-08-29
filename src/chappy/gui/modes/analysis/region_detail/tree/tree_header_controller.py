"""Controller for optimize tree column width, visibility, and order customization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QHeaderView

from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    COLUMNS,
    DEFAULT_PROFILE,
    TreeColumnProfile,
)
from chappy.gui.theme import create_styled_menu

if TYPE_CHECKING:
    from PySide6.QtCore import QByteArray, QPoint
    from PySide6.QtWidgets import QTreeWidget, QWidget

# Logical column that carries the tree's expand/collapse decoration and must
# stay pinned to the leftmost visual position (moving it makes the arrow
# position non-intuitive).
_LOCKED_LOGICAL_COLUMN = 0

# Free-text column that absorbs leftover viewport width; per ADR
# optimize-table-column-display §2 a Stretch role would forbid manual resizing,
# so the slack is distributed explicitly and the column stays Interactive.
_SPECIES_COLUMN_KEY = "SPECIES"

# Numeric and bounded-text columns that continuously track their content.
# The row count is bounded by the component count, so ResizeToContents cannot
# degenerate into large row scans here.
_CONTENT_SIZED_COLUMN_KEYS = frozenset(
    {"ID", "Z", "LOGN", "B", "CF", "ANALYSIS_HALF_WIDTH", "WAVELENGTH", "LOOKBACK", "COMOVING"}
)

# Sample text bounding the narrowest acceptable section (keeps λ readable).
_MINIMUM_SECTION_SAMPLE = "9999.99"

# Frame and cell-margin allowance added to the minimum section sample width.
_MINIMUM_SECTION_PADDING = 12

# Sample text bounding the content-derived species width, so one pathological
# multiplet label cannot push the numeric columns out of the viewport.
_SPECIES_CONTENT_WIDTH_SAMPLE = "Mg II 2796/2803/2852"


@dataclass(frozen=True)
class SavedTreeHeader:
    """Persisted header layout plus who decided the species column width."""

    state: QByteArray
    schema: str
    species_width_pinned: bool


class OptimizeTreeHeaderPort(Protocol):
    """Panel operations required by tree header customization."""

    def load_tree_header_state(self) -> SavedTreeHeader | None:
        """Return the persisted header layout, if any."""
        ...

    def save_tree_header_state(self, saved: SavedTreeHeader) -> None:
        """Persist the header layout."""
        ...


def tree_header_schema() -> str:
    """Return the column-key schema used to validate persisted header state."""
    return ",".join(meta.key for meta in COLUMNS)


class OptimizeTreeHeaderController:
    """Coordinate optimize parameter tree column width, visibility, and order."""

    def __init__(
        self, *, tree: QTreeWidget, parent: QWidget, port: OptimizeTreeHeaderPort
    ) -> None:
        """Initialize the header controller and wire header signals.

        Args:
            tree: Parameter tree widget whose header is customized.
            parent: Parent widget for the visibility menu.
            port: Persistence boundary for header state.
        """
        self._tree = tree
        self._parent = parent
        self._port = port
        self._guarding_locked_move = False
        self._applying_layout = False
        self._species_width_pinned = False

        header = tree.header()
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_visibility_menu)
        header.sectionMoved.connect(self._on_section_moved)
        header.sectionResized.connect(self._on_section_resized)

    def initialize(self, *, profile: TreeColumnProfile = DEFAULT_PROFILE) -> None:
        """Restore persisted header state, or apply a default column profile.

        Nothing is persisted here: the default profile is derived from
        ``profile`` on every launch, so writing it back would freeze the shipped
        default for existing users. Persistence starts at the first user edit.

        Args:
            profile: Column visibility/order profile applied when no valid
                persisted state exists. Overridable for tests and alternate
                shipped defaults.
        """
        saved = self._port.load_tree_header_state()
        header = self._tree.header()
        self._applying_layout = True
        try:
            if saved is not None and saved.schema == tree_header_schema():
                header.restoreState(saved.state)
                self._species_width_pinned = saved.species_width_pinned
            else:
                self._apply_profile(profile)
            # Restored states may carry legacy resize modes; the sizing
            # policy is normative and must win over persisted modes.
            self._apply_size_policy()
        finally:
            self._applying_layout = False

    def _apply_size_policy(self) -> None:
        """Apply per-column resize modes per ADR optimize-table-column-display §2.

        Numeric columns track their bounded content, SPECIES stays Interactive
        so users can resize it and so the slack distribution can drive it, and a
        minimum section size keeps narrow numeric columns (e.g. λ) readable.
        """
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(
            header.fontMetrics().horizontalAdvance(_MINIMUM_SECTION_SAMPLE)
            + _MINIMUM_SECTION_PADDING
        )
        for column, meta in enumerate(COLUMNS):
            if meta.key in _CONTENT_SIZED_COLUMN_KEYS:
                mode = QHeaderView.ResizeMode.ResizeToContents
            else:
                mode = QHeaderView.ResizeMode.Interactive
            header.setSectionResizeMode(column, mode)

    def _apply_profile(self, profile: TreeColumnProfile) -> None:
        """Apply a column profile's visibility and visual order to the header."""
        for column, meta in enumerate(COLUMNS):
            self._tree.setColumnHidden(column, meta.key in profile.hidden_keys)

        if profile.visual_order is None:
            return

        header = self._tree.header()
        key_to_column = {meta.key: column for column, meta in enumerate(COLUMNS)}
        self._guarding_locked_move = True
        try:
            for target_visual, key in enumerate(profile.visual_order):
                mapped_column = key_to_column.get(key)
                if mapped_column is None:
                    continue
                current_visual = header.visualIndex(mapped_column)
                if current_visual != target_visual:
                    header.moveSection(current_visual, target_visual)
        finally:
            self._guarding_locked_move = False

    def on_tree_populated(self) -> None:
        """Refresh content-tracked section widths after a populated render.

        Content-sized sections normally follow row changes automatically; an
        explicit pass here replaces header-only placeholder widths as soon as
        the first real rows are rendered instead of on the next layout event.
        """
        if self._tree.topLevelItemCount() == 0:
            return
        self._applying_layout = True
        try:
            self._tree.header().resizeSections()
        finally:
            self._applying_layout = False
        self._fit_species_column()

    def _species_column(self) -> int | None:
        """Return the logical index of the species column, if it exists."""
        return next(
            (column for column, meta in enumerate(COLUMNS) if meta.key == _SPECIES_COLUMN_KEY),
            None,
        )

    def on_viewport_resized(self) -> None:
        """Re-distribute the leftover viewport width after the tree is resized."""
        self._fit_species_column()

    def _fit_species_column(self) -> None:
        """Widen the species column into the leftover viewport width.

        The column keeps at least its content-derived width, so a viewport too
        narrow for every column still scrolls horizontally rather than eliding
        species names. A width the user set by dragging wins permanently.
        """
        if self._species_width_pinned:
            return

        species_column = self._species_column()
        if species_column is None or self._tree.isColumnHidden(species_column):
            return

        header = self._tree.header()
        other_columns_width = sum(
            header.sectionSize(column)
            for column in range(header.count())
            if column != species_column and not header.isSectionHidden(column)
        )
        target = max(
            self._species_content_width(species_column),
            self._tree.viewport().width() - other_columns_width,
            header.minimumSectionSize(),
        )
        if target == header.sectionSize(species_column):
            return

        self._applying_layout = True
        try:
            header.resizeSection(species_column, target)
        finally:
            self._applying_layout = False

    def _species_content_width(self, species_column: int) -> int:
        """Return the species width its rendered labels ask for, sample-capped."""
        header = self._tree.header()
        return min(
            self._tree.sizeHintForColumn(species_column) + _MINIMUM_SECTION_PADDING,
            header.fontMetrics().horizontalAdvance(_SPECIES_CONTENT_WIDTH_SAMPLE)
            + _MINIMUM_SECTION_PADDING,
        )

    def _on_section_moved(
        self, logical_index: int, old_visual_index: int, new_visual_index: int
    ) -> None:
        """Undo moves of the locked column and persist other reorders."""
        if self._guarding_locked_move:
            return

        if logical_index == _LOCKED_LOGICAL_COLUMN:
            header = self._tree.header()
            self._guarding_locked_move = True
            try:
                header.moveSection(new_visual_index, old_visual_index)
            finally:
                self._guarding_locked_move = False
            return

        self._save_header_state()

    def _on_section_resized(self, logical_index: int, _old_size: int, _new_size: int) -> None:
        """Pin a species width the user dragged, so auto-fitting stops there.

        Only a resize made with a mouse button down is the user's decision;
        everything else is Qt or this controller reflowing the columns.
        """
        if not self._dragging_species(logical_index):
            return
        self._species_width_pinned = True
        self._save_header_state()

    def _dragging_species(self, logical_index: int) -> bool:
        """Return whether this resize is the user dragging the species handle."""
        return (
            not self._applying_layout
            and logical_index == self._species_column()
            and QApplication.mouseButtons() != Qt.MouseButton.NoButton
        )

    def _save_header_state(self) -> None:
        header = self._tree.header()
        self._port.save_tree_header_state(
            SavedTreeHeader(
                state=header.saveState(),
                schema=tree_header_schema(),
                species_width_pinned=self._species_width_pinned,
            )
        )

    def _show_visibility_menu(self, point: QPoint) -> None:
        """Show a checkable menu toggling visibility of non-locked columns."""
        header = self._tree.header()
        header_item = self._tree.headerItem()
        menu = create_styled_menu(self._parent)
        for column in range(len(COLUMNS)):
            if column == _LOCKED_LOGICAL_COLUMN:
                continue

            label = header_item.text(column) if header_item is not None else COLUMNS[column].key
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(not self._tree.isColumnHidden(column))
            action.toggled.connect(
                lambda checked, column=column: self._set_column_visible(column, checked)
            )
            menu.addAction(action)

        menu.exec(header.mapToGlobal(point))

    def _set_column_visible(self, column: int, visible: bool) -> None:
        self._tree.setColumnHidden(column, not visible)
        self._save_header_state()
        self._fit_species_column()
