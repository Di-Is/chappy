"""Tests for the identify preset list dialog baseline interactions."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast

import pytest
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.infrastructure.preset_store import PersistentPresetStore
from chappy.gui.modes.identify.presets.preset_list_dialog import PresetListDialog
from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
from scripts.i18n_lupdate import run_lupdate


_DEFAULT_TRANSLATIONS = {
    "Lyman Series": "Lyman Series",
    "Principal H I Lyman transitions for quick selection.": (
        "Principal H I Lyman transitions for quick selection."
    ),
    "Metal Lines": "Metal Lines",
    "Metal doublets.": "Metal doublets.",
}


def _preset_translate(source_text: str) -> str:
    normalized = str(source_text)
    try:
        return _DEFAULT_TRANSLATIONS[normalized]
    except KeyError as exc:  # pragma: no cover - catches new translation keys in tests
        raise KeyError(f"Missing test translation for '{normalized}'") from exc


class _StubAtomicData:
    """Minimal atomic data provider for dialog tests."""

    def __init__(self, lines: list[AtomicLine]) -> None:
        self.lines = lines
        self._index = {line.line_id: line for line in lines}

    def get_line_by_id(self, line_id: str | None) -> AtomicLine | None:
        if line_id is None:
            return None
        return self._index.get(line_id)


def _make_line(
    identifier: str, species: str, wavelength: float, osc: float, *, multiplet_id: str = ""
) -> AtomicLine:
    return AtomicLine(
        line_identifier=identifier,
        species=species,
        wavelength_angstrom=wavelength,
        oscillator_strength=0.1,
        gamma_value=1e8,
        multiplet_id=multiplet_id,
        comments="",
        element_symbol=species.split()[0],
        charge_state=None,
        transition_name=f"{species} {wavelength:.1f}",
        multiplet_label="",
    )


def test_baseline_change_invokes_single_update(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    line_a = _make_line("line:a", "H I", 1215.6701, 0.416)
    line_b = _make_line("line:b", "C IV", 1548.1950, 0.286)
    atomic_data = cast(AtomicLineData, _StubAtomicData([line_a, line_b]))

    store = PersistentPresetStore(
        atomic_data=atomic_data,
        storage_path=tmp_path / "presets.json",
        translate=_preset_translate,
    )
    preset = store.create_custom_preset(
        "Custom baseline", line_ids=[line_a.line_id, line_b.line_id]
    )

    preset_store = IdentifyPresetStore(store)

    dialog = PresetListDialog(None, preset_store, atomic_data=atomic_data)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    # Ensure the dialog has selected the custom preset created above
    qtbot.waitUntil(lambda: dialog._current_preset_id == preset.id)

    assert dialog._baseline_combo.count() == 2, "Expected two baseline choices"

    original_index = dialog._baseline_combo.currentIndex()
    other_index = 1 if original_index == 0 else 0

    # First change uses the original preset_store method to verify stability in both directions.
    dialog._baseline_combo.setCurrentIndex(other_index)
    qtbot.waitUntil(lambda: dialog._baseline_combo.currentIndex() == other_index)

    original_method = preset_store.set_baseline

    call_count = 0

    def spy(preset_id: str, line_id: str | None) -> None:
        nonlocal call_count
        call_count += 1
        original_method(preset_id, line_id)

    monkeypatch.setattr(preset_store, "set_baseline", spy)

    target_index = original_index
    dialog._baseline_combo.setCurrentIndex(target_index)

    qtbot.waitUntil(lambda: call_count == 1)
    assert call_count == 1

    updated = preset_store.get_preset(preset.id)
    assert updated is not None
    expected_line = dialog._baseline_combo.itemData(dialog._baseline_combo.currentIndex())
    assert updated.baseline_id == expected_line


def test_invalid_preset_item_payload_fails_fast(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unexpected preset item payload should fail at the Qt boundary."""
    line = _make_line("line:a", "H I", 1215.6701, 0.416)
    atomic_data = cast(AtomicLineData, _StubAtomicData([line]))
    store = PersistentPresetStore(
        atomic_data=atomic_data,
        storage_path=tmp_path / "presets.json",
        translate=_preset_translate,
    )
    store.create_custom_preset("Custom", line_ids=[line.line_id])
    preset_store = IdentifyPresetStore(store)
    dialog = PresetListDialog(None, preset_store, atomic_data=atomic_data)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: dialog._preset_list.currentItem() is not None)

    item = dialog._preset_list.currentItem()
    assert item is not None
    item.setData(Qt.ItemDataRole.UserRole, object())

    with pytest.raises(TypeError, match="Preset id item data"):
        dialog._on_preset_selection_changed()


def _select_rows(dialog: PresetListDialog, line_ids: set[str]) -> None:
    """Select the table rows whose display payload matches the given line ids."""
    selection_model = dialog._line_table.selectionModel()
    assert selection_model is not None
    selection_model.clearSelection()
    flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows
    for row in range(dialog._line_table.rowCount()):
        item = dialog._line_table.item(row, 0)
        display = item.data(Qt.ItemDataRole.UserRole) if item else None
        if display is not None and display.identifier in line_ids:
            selection_model.select(dialog._line_table.model().index(row, 0), flags)


def test_tie_group_card_creates_and_removes_group(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The dialog links and unlinks tie groups from row selection."""
    line_a = _make_line("line:a", "C IV", 1548.2, 0.3, multiplet_id="civ")
    line_b = _make_line("line:b", "C IV", 1550.8, 0.1, multiplet_id="civ")
    atomic_data = cast(AtomicLineData, _StubAtomicData([line_a, line_b]))
    persistent_store = PersistentPresetStore(
        atomic_data=atomic_data,
        storage_path=tmp_path / "presets.json",
        translate=_preset_translate,
    )
    preset = persistent_store.create_custom_preset(
        "Custom", line_ids=[line_a.line_id, line_b.line_id]
    )
    preset_store = IdentifyPresetStore(persistent_store)
    dialog = PresetListDialog(None, preset_store, atomic_data=atomic_data)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: dialog._current_preset_id == preset.id)

    _select_rows(dialog, {line_a.line_id, line_b.line_id})
    assert dialog._link_button.isEnabled()
    dialog._link_button.click()

    updated = preset_store.get_preset(preset.id)
    assert updated is not None
    assert len(updated.tie_groups) == 1

    _select_rows(dialog, {line_a.line_id})
    assert dialog._unlink_button.isEnabled()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )
    dialog._unlink_button.click()
    assert preset_store.get_preset(preset.id).tie_groups == []  # type: ignore[union-attr]


def test_link_and_unlink_disabled_for_builtin_preset(qtbot: QtBot, tmp_path: Path) -> None:
    """Link/Unlink must stay disabled while a read-only preset is selected."""
    lyman_line_ids = (
        "8cd0394ff25e72e7",
        "cd0f85d159976946",
        "2feafb6deab92064",
        "35815e9743604328",
        "9f1f1a3dae473067",
    )
    lyman_lines = [
        _make_line(line_id, "H I", 1215.6701 - index, 0.416)
        for index, line_id in enumerate(lyman_line_ids)
    ]
    atomic_data = cast(AtomicLineData, _StubAtomicData(lyman_lines))
    store = PersistentPresetStore(
        atomic_data=atomic_data,
        storage_path=tmp_path / "presets.json",
        translate=_preset_translate,
    )
    preset_store = IdentifyPresetStore(store)
    builtin_preset = next(preset for preset in store.list_presets() if not preset.is_editable)

    dialog = PresetListDialog(None, preset_store, atomic_data=atomic_data)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    dialog._select_preset_in_list(builtin_preset.id)
    qtbot.waitUntil(lambda: dialog._current_preset_id == builtin_preset.id)

    assert dialog._line_table.rowCount() > 0
    dialog._line_table.selectAll()

    assert not dialog._link_button.isEnabled()
    assert not dialog._unlink_button.isEnabled()
    assert not dialog._add_line_button.isEnabled()
    assert not dialog._remove_line_button.isEnabled()


def test_suggestion_bar_shows_and_applies_all(qtbot: QtBot, tmp_path: Path) -> None:
    """The suggestion info bar appears for ungrouped multiplets and Apply all links them."""
    line_a = _make_line("line:a", "C IV", 1548.2, 0.3, multiplet_id="civ")
    line_b = _make_line("line:b", "C IV", 1550.8, 0.1, multiplet_id="civ")
    atomic_data = cast(AtomicLineData, _StubAtomicData([line_a, line_b]))
    store = PersistentPresetStore(
        atomic_data=atomic_data,
        storage_path=tmp_path / "presets.json",
        translate=_preset_translate,
    )
    preset = store.create_custom_preset("Custom", line_ids=[line_a.line_id, line_b.line_id])
    preset_store = IdentifyPresetStore(store)
    dialog = PresetListDialog(None, preset_store, atomic_data=atomic_data)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: dialog._current_preset_id == preset.id)

    assert dialog._suggestion_bar.isVisible()
    assert len(dialog._current_suggestions) == 1

    dialog._apply_suggestions_button.click()

    updated = preset_store.get_preset(preset.id)
    assert updated is not None
    assert len(updated.tie_groups) == 1
    assert not dialog._suggestion_bar.isVisible()


def test_invalid_baseline_item_payload_fails_fast(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unexpected baseline item payload should fail at the Qt boundary."""
    line = _make_line("line:a", "H I", 1215.6701, 0.416)
    atomic_data = cast(AtomicLineData, _StubAtomicData([line]))
    store = PersistentPresetStore(
        atomic_data=atomic_data,
        storage_path=tmp_path / "presets.json",
        translate=_preset_translate,
    )
    preset = store.create_custom_preset("Custom", line_ids=[line.line_id])
    preset_store = IdentifyPresetStore(store)
    dialog = PresetListDialog(None, preset_store, atomic_data=atomic_data)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: dialog._current_preset_id == preset.id)

    dialog._baseline_combo.setItemData(0, object())

    with pytest.raises(TypeError, match="Baseline line id item data"):
        dialog._on_baseline_changed(0)


def test_preset_list_dialog_requires_atomic_data(qapp: object) -> None:
    """Atomic data is a required composition dependency."""
    preset_store = IdentifyPresetStore(
        PersistentPresetStore(AtomicLineData(), translate=_preset_translate)
    )

    with pytest.raises(TypeError, match="atomic_data"):
        PresetListDialog(None, preset_store)


def test_lupdate_extracts_preset_list_dialog_migrated_gui_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts the migrated PresetListDialog GUI sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "chappy_ja.ts"
    run_lupdate(
        source_dirs=[Path("src/chappy/gui/modes/identify/presets/preset_list_dialog.py")],
        ts_output=ts_path,
    )

    root = ET.parse(ts_path).getroot()
    sources = {
        source.text
        for source in root.findall("./context/message/source")
        if source.text is not None
    }
    assert {
        "Absorption Preset Management",
        "Close",
        "Presets",
        "New",
        "Rename",
        "Duplicate",
        "Delete",
        "Import...",
        "Export...",
        "Add Line",
        "Remove Selected",
        "Link selected lines",
        "Unlink",
        "Apply all",
        "Reference line:",
        "Line",
        "Wavelength (Å)",
        "f-value",
        "Link",
        "Selected: None",
        "Total 0 lines",
        "{name} (read-only)",
        "Unknown",
        "Total {count} lines",
        "{count} suggested link(s) from the line database.",
        "Unknown line ({id})",
        "System preset (read-only)",
        "Remove {count} selected lines?",
        "Confirm Removal",
        "Remove the selected link?",
        "Baseline Error",
        "New Preset",
        "Preset Error",
        "Preset Limit",
        "Rename Preset",
        "Delete preset '{name}'?",
        "Confirm Deletion",
        "JSON Files (*.json)",
        "Enter preset name:",
    } <= sources
    assert not any("GUI__" in source or "DLG__" in source for source in sources)
