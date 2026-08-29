"""Integration checks for bundled declarative preset groups."""

from __future__ import annotations

from pathlib import Path

from chappy.core.presets import PresetStore
from chappy.infrastructure.atomic_lines import load_atomic_data


def _store() -> PresetStore:
    root = Path(__file__).parents[2]
    data = load_atomic_data(root / "spectral_database/db_file/spectral_lines.csv")
    return PresetStore(data, translate=lambda text: text)


def test_builtin_lyman_uses_plain_series_lines_in_one_tie_group() -> None:
    preset = _store().get_preset("builtin:lyman")
    assert preset is not None
    assert preset.line_ids == [
        "8cd0394ff25e72e7",
        "cd0f85d159976946",
        "2feafb6deab92064",
        "35815e9743604328",
        "9f1f1a3dae473067",
    ]
    assert preset.baseline_id == "8cd0394ff25e72e7"
    assert len(preset.tie_groups) == 1
    assert preset.tie_groups[0].line_ids == tuple(preset.line_ids)


def test_builtin_metal_doublets_define_four_groups() -> None:
    preset = _store().get_preset("builtin:metal_doublets")
    assert preset is not None
    assert len(preset.tie_groups) == 4
    members = [line_id for group in preset.tie_groups for line_id in group.line_ids]
    assert len(members) == len(set(members)) == 8


def test_builtin_group_uids_are_stable() -> None:
    first = {
        preset.id: tuple(group.uid for group in preset.tie_groups)
        for preset in _store().list_presets()
    }
    second = {
        preset.id: tuple(group.uid for group in preset.tie_groups)
        for preset in _store().list_presets()
    }
    assert first == second
    assert all(
        len(uid) == 32 and all(char in "0123456789abcdef" for char in uid)
        for uids in first.values()
        for uid in uids
    )
