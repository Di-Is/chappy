"""Tests for optimize tree header controller."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHeaderView, QTreeWidget, QTreeWidgetItem, QWidget

from chappy.gui.modes.analysis.region_detail.tree import (
    tree_header_controller as header_controller_module,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_columns import (
    CITIZEN_SCIENTIST_PROFILE,
    COL_INDEX,
    COLUMNS,
    ColumnMeta,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_header_controller import (
    OptimizeTreeHeaderController,
    SavedTreeHeader,
    tree_header_schema,
)
from chappy.gui.modes.analysis.region_detail.tree.tree_widget import OptimizeTreeWidget


@pytest.fixture(name="qapp")
def fixture_qapp() -> QApplication:
    """Provide a QApplication instance for Qt widgets."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Port:
    """Tree header port test double."""

    def __init__(self, *, saved: SavedTreeHeader | None = None) -> None:
        self._saved = saved
        self.save_calls: list[SavedTreeHeader] = []

    def load_tree_header_state(self) -> SavedTreeHeader | None:
        """Return the configured header layout."""
        return self._saved

    def save_tree_header_state(self, saved: SavedTreeHeader) -> None:
        """Record a persisted header layout."""
        self.save_calls.append(saved)


def _tree(qapp: QApplication, parent: QWidget) -> OptimizeTreeWidget:
    """Return a tree widget matching the production column layout."""
    assert qapp is not None
    tree = OptimizeTreeWidget(parent=parent)
    tree.setColumnCount(len(COLUMNS))
    tree.setHeaderLabels([meta.key for meta in COLUMNS])
    return tree


def _populate(
    qapp: QApplication, tree: QTreeWidget, controller: OptimizeTreeHeaderController, width: int
) -> None:
    """Render one species row and settle the layout at the requested width."""
    item = QTreeWidgetItem(tree)
    item.setText(COL_INDEX["SPECIES"], "Mg II 2796/2803")
    tree.resize(width, 300)
    tree.window().show()
    tree.show()
    qapp.processEvents()
    controller.on_tree_populated()
    qapp.processEvents()


def _drag_species_width(qapp: QApplication, tree: QTreeWidget, width: int) -> None:
    """Resize the species section the way a header drag does."""
    header = tree.header()
    QTest.mousePress(header.viewport(), Qt.MouseButton.LeftButton)
    header.resizeSection(COL_INDEX["SPECIES"], width)
    QTest.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton)
    qapp.processEvents()


def _visible_sections_width(tree: QTreeWidget) -> int:
    """Return the total width of the header's visible sections."""
    header = tree.header()
    return sum(
        header.sectionSize(column)
        for column in range(header.count())
        if not header.isSectionHidden(column)
    )


def test_locked_column_move_is_reverted(qapp: QApplication) -> None:
    """Moving logical column 0 out of place should be undone."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)

    header = tree.header()
    header.moveSection(0, 3)

    assert controller is not None
    assert header.visualIndex(0) == 0


def test_non_locked_column_move_persists_state(qapp: QApplication) -> None:
    """Moving a non-locked column should be kept and persisted."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)

    header = tree.header()
    header.moveSection(1, 3)

    assert controller is not None
    assert header.visualIndex(1) == 3
    assert port.save_calls
    assert port.save_calls[-1].schema == tree_header_schema()


def test_visibility_toggle_hides_column_and_saves(qapp: QApplication) -> None:
    """Toggling a column's visibility should hide it and persist state."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)

    controller._set_column_visible(1, False)

    assert tree.isColumnHidden(1)
    assert port.save_calls
    assert port.save_calls[-1].schema == tree_header_schema()


def test_initialize_restores_matching_saved_state(qapp: QApplication) -> None:
    """A schema-matching saved state should be restored via restoreState."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller._set_column_visible(1, False)
    saved = port.save_calls[-1]

    fresh_tree = _tree(qapp, parent)
    restore_port = _Port(saved=saved)
    OptimizeTreeHeaderController(tree=fresh_tree, parent=parent, port=restore_port).initialize()

    assert fresh_tree.isColumnHidden(1)


def test_initialize_falls_back_to_defaults_on_schema_mismatch(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema mismatch should discard saved state and apply the default profile."""
    custom_columns = (
        ColumnMeta("ID", "ID"),
        ColumnMeta("LOOKBACK", "Lookback"),
        ColumnMeta("VISIBLE", "Visible"),
    )
    monkeypatch.setattr(header_controller_module, "COLUMNS", custom_columns)

    parent = QWidget()
    tree = QTreeWidget(parent)
    tree.setColumnCount(len(custom_columns))
    tree.setHeaderLabels([meta.key for meta in custom_columns])

    port = _Port(
        saved=SavedTreeHeader(
            state=QByteArray(b"stale-state"), schema="stale-schema", species_width_pinned=True
        )
    )
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller.initialize()

    assert not tree.isColumnHidden(1)
    assert not tree.isColumnHidden(2)


def test_initialize_applies_defaults_without_persisting(qapp: QApplication) -> None:
    """No persisted state should apply the profile and write nothing back.

    The default profile is re-derived on every launch, so persisting it here
    would freeze the shipped default for existing users.
    """
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)

    controller.initialize()

    for column, meta in enumerate(COLUMNS):
        assert tree.isColumnHidden(column) == (not meta.visible_by_default)
    assert not port.save_calls


def test_default_profile_shows_cosmology_columns_next_to_z(qapp: QApplication) -> None:
    """The default profile should show t_lb/D_C right after z."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)

    controller.initialize()

    assert not tree.isColumnHidden(COL_INDEX["LOOKBACK"])
    assert not tree.isColumnHidden(COL_INDEX["COMOVING"])

    header = tree.header()
    z_visual = header.visualIndex(COL_INDEX["Z"])
    assert header.visualIndex(COL_INDEX["LOOKBACK"]) == z_visual + 1
    assert header.visualIndex(COL_INDEX["COMOVING"]) == z_visual + 2


def test_initialize_applies_content_and_interactive_size_policy(qapp: QApplication) -> None:
    """Bounded columns track content, SPECIES stays user-resizable, λ cannot collapse."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)

    controller.initialize()

    header = tree.header()
    assert not header.stretchLastSection()
    assert header.minimumSectionSize() > 0
    assert header.sectionResizeMode(COL_INDEX["SPECIES"]) == QHeaderView.ResizeMode.Interactive
    for key in (
        "ID",
        "Z",
        "LOGN",
        "B",
        "CF",
        "ANALYSIS_HALF_WIDTH",
        "WAVELENGTH",
        "LOOKBACK",
        "COMOVING",
    ):
        assert header.sectionResizeMode(COL_INDEX[key]) == QHeaderView.ResizeMode.ResizeToContents


def test_initialize_reapplies_size_policy_over_restored_state(qapp: QApplication) -> None:
    """A restored persisted state must not undo the normative sizing policy."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller._set_column_visible(1, False)
    saved = port.save_calls[-1]

    fresh_tree = _tree(qapp, parent)
    restore_port = _Port(saved=saved)
    OptimizeTreeHeaderController(tree=fresh_tree, parent=parent, port=restore_port).initialize()

    header = fresh_tree.header()
    assert not header.stretchLastSection()
    assert header.sectionResizeMode(COL_INDEX["SPECIES"]) == QHeaderView.ResizeMode.Interactive
    assert (
        header.sectionResizeMode(COL_INDEX["WAVELENGTH"])
        == QHeaderView.ResizeMode.ResizeToContents
    )


def test_species_column_absorbs_leftover_viewport_width(qapp: QApplication) -> None:
    """A viewport wider than the columns should leave no gap beside SPECIES."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller.initialize()

    _populate(qapp, tree, controller, width=1600)

    header = tree.header()
    assert header.sectionSize(COL_INDEX["SPECIES"]) > tree.sizeHintForColumn(COL_INDEX["SPECIES"])
    assert _visible_sections_width(tree) == tree.viewport().width()


def test_species_column_keeps_content_width_in_a_narrow_viewport(qapp: QApplication) -> None:
    """A viewport too narrow for the columns should scroll, not squeeze SPECIES."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller.initialize()

    _populate(qapp, tree, controller, width=320)

    header = tree.header()
    assert header.sectionSize(COL_INDEX["SPECIES"]) >= tree.sizeHintForColumn(COL_INDEX["SPECIES"])
    assert _visible_sections_width(tree) > tree.viewport().width()


def test_viewport_resize_refits_the_species_column(qapp: QApplication) -> None:
    """Widening the window should hand the new space to SPECIES."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller.initialize()
    tree.viewport_resized.connect(controller.on_viewport_resized)

    _populate(qapp, tree, controller, width=1200)
    narrow_width = tree.header().sectionSize(COL_INDEX["SPECIES"])

    tree.resize(1800, 300)
    qapp.processEvents()
    qapp.processEvents()

    assert tree.header().sectionSize(COL_INDEX["SPECIES"]) > narrow_width
    assert _visible_sections_width(tree) == tree.viewport().width()


def test_manual_species_resize_is_pinned_and_persisted(qapp: QApplication) -> None:
    """A dragged SPECIES width should survive later renders and viewport resizes."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller.initialize()
    _populate(qapp, tree, controller, width=1600)

    _drag_species_width(qapp, tree, 234)
    controller.on_tree_populated()
    tree.resize(1800, 300)
    qapp.processEvents()

    assert tree.header().sectionSize(COL_INDEX["SPECIES"]) == 234
    assert port.save_calls
    assert port.save_calls[-1].species_width_pinned


def test_pinned_species_width_survives_a_restore(qapp: QApplication) -> None:
    """A restored pinned width must not be re-fitted to the viewport."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller.initialize()
    _drag_species_width(qapp, tree, 234)
    saved = port.save_calls[-1]

    fresh_tree = _tree(qapp, parent)
    restored = OptimizeTreeHeaderController(
        tree=fresh_tree, parent=parent, port=_Port(saved=saved)
    )
    restored.initialize()
    _populate(qapp, fresh_tree, restored, width=1600)

    assert fresh_tree.header().sectionSize(COL_INDEX["SPECIES"]) == 234


def test_unpinned_species_width_is_refitted_after_a_restore(qapp: QApplication) -> None:
    """A stale unpinned width must not outlive the session that produced it."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)
    controller.initialize()
    controller._set_column_visible(COL_INDEX["LOOKBACK"], False)
    saved = port.save_calls[-1]
    assert not saved.species_width_pinned

    fresh_tree = _tree(qapp, parent)
    restored = OptimizeTreeHeaderController(
        tree=fresh_tree, parent=parent, port=_Port(saved=saved)
    )
    restored.initialize()
    _populate(qapp, fresh_tree, restored, width=1600)

    assert _visible_sections_width(fresh_tree) == fresh_tree.viewport().width()


def test_citizen_scientist_profile_shows_and_reorders_cosmology_columns(
    qapp: QApplication,
) -> None:
    """The citizen-scientist profile should show t_lb/D_C right after z."""
    parent = QWidget()
    tree = _tree(qapp, parent)
    port = _Port()
    controller = OptimizeTreeHeaderController(tree=tree, parent=parent, port=port)

    controller.initialize(profile=CITIZEN_SCIENTIST_PROFILE)

    assert not tree.isColumnHidden(COL_INDEX["LOOKBACK"])
    assert not tree.isColumnHidden(COL_INDEX["COMOVING"])

    header = tree.header()
    z_visual = header.visualIndex(COL_INDEX["Z"])
    lookback_visual = header.visualIndex(COL_INDEX["LOOKBACK"])
    comoving_visual = header.visualIndex(COL_INDEX["COMOVING"])
    assert lookback_visual == z_visual + 1
    assert comoving_visual == z_visual + 2
