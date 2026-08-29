"""Checks that the bundled CSV matches the declarative built-in presets."""

from __future__ import annotations

from pathlib import Path

from chappy.infrastructure.atomic_lines import load_atomic_data


def test_bundled_database_contains_plain_lyman_lines_without_legacy_mlt_rows() -> None:
    root = Path(__file__).parents[2]
    data = load_atomic_data(root / "spectral_database/db_file/spectral_lines.csv")
    plain_ids = {
        "8cd0394ff25e72e7",
        "cd0f85d159976946",
        "2feafb6deab92064",
        "35815e9743604328",
        "9f1f1a3dae473067",
    }
    legacy_ids = {
        "41a9625cec8cf0f0",
        "b30fa388ea9bd571",
        "f0c8118c47920f8e",
        "796715ac31bf9dac",
        "d8c985027ec30cbe",
    }
    assert all(data.get_line_by_id(line_id) is not None for line_id in plain_ids)
    assert all(data.get_line_by_id(line_id) is None for line_id in legacy_ids)
    assert all(
        not (data.get_line_by_id(line_id).transition_name.endswith("-mlt"))
        for line_id in plain_ids
    )  # type: ignore[union-attr]
    assert all(data.get_line_by_id(line_id).multiplet_id == "" for line_id in plain_ids)  # type: ignore[union-attr]
