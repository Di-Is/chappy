"""Persistence tests for :mod:`chappy.core.presets`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.infrastructure.preset_store import PRESET_FILE_SCHEMA_VERSION, PersistentPresetStore


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
    except KeyError as exc:  # pragma: no cover - guards unexpected keys in tests
        raise KeyError(f"Missing test translation for '{normalized}'") from exc


class _StubAtomicData:
    """Minimal atomic data implementation for persistence tests."""

    def __init__(self, lines: list[AtomicLine]) -> None:
        self.lines = lines
        self._index = {line.line_id: line for line in lines}

    def get_line_by_id(self, line_id: str | None) -> AtomicLine | None:
        if line_id is None:
            return None
        return self._index.get(line_id)


def _make_line(identifier: str, species: str, wavelength: float, osc: float) -> AtomicLine:
    return AtomicLine(
        line_identifier=identifier,
        species=species,
        wavelength_angstrom=wavelength,
        oscillator_strength=0.1,
        gamma_value=1e8,
        multiplet_id="",
        comments="",
        element_symbol=species.split()[0],
        charge_state=None,
        transition_name=f"{species} {wavelength:.1f}",
        multiplet_label="",
    )


def _atomic_data(lines: list[AtomicLine]) -> AtomicLineData:
    """Return test atomic data cast to the store constructor type."""
    return cast(AtomicLineData, _StubAtomicData(lines))


def test_preset_groups_roundtrip_through_json(tmp_path: Path) -> None:
    lines = [_make_line("a", "C IV", 1548.2, 0.1), _make_line("b", "C IV", 1550.8, 0.1)]
    path = tmp_path / "presets.json"
    store = PersistentPresetStore(
        _atomic_data(lines), storage_path=path, translate=_preset_translate
    )
    preset = store.create_custom_preset("Custom", line_ids=["a", "b"])
    group = store.add_tie_group(preset.id, ["a", "b"])

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == PRESET_FILE_SCHEMA_VERSION == "1.2"
    assert payload["presets"][0]["groups"] == [{"uid": group.uid, "line_ids": ["a", "b"]}]

    loaded = PersistentPresetStore(
        _atomic_data(lines), storage_path=path, translate=_preset_translate
    ).get_preset(preset.id)
    assert loaded is not None
    assert loaded.tie_groups == [group]


def test_legacy_unknown_lines_are_removed_and_warned(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    lines = [_make_line("a", "C IV", 1548.2, 0.1), _make_line("b", "C IV", 1550.8, 0.1)]
    path = tmp_path / "presets.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "app_version": "0.0.0",
                "presets": [
                    {
                        "id": "custom",
                        "name": "Legacy",
                        "source": "custom",
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "baseline_id": "41a9625cec8cf0f0",
                        "lines": [
                            {"line_id": "a"},
                            {"line_id": "41a9625cec8cf0f0"},
                            {"line_id": "b"},
                        ],
                        "groups": [
                            {"uid": "legacy-group", "line_ids": ["a", "41a9625cec8cf0f0", "b"]}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with caplog.at_level("WARNING"):
        store = PersistentPresetStore(
            _atomic_data(lines), storage_path=path, translate=_preset_translate
        )

    loaded = store.get_preset("custom")
    assert loaded is not None
    assert loaded.line_ids == ["a", "b"]
    assert loaded.baseline_id == "a"
    assert loaded.tie_groups[0].line_ids == ("a", "b")
    assert "41a9625cec8cf0f0" in caplog.text


def test_import_of_only_unknown_lines_is_skipped(tmp_path: Path) -> None:
    lines = [_make_line("a", "C IV", 1548.2, 0.1)]
    path = tmp_path / "presets.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "app_version": "0.0.0",
                "presets": [{"name": "Legacy", "lines": [{"line_id": "41a9625cec8cf0f0"}]}],
            }
        ),
        encoding="utf-8",
    )
    store = PersistentPresetStore(_atomic_data(lines), translate=_preset_translate)
    summary = store.import_presets(path)
    assert summary.skipped == 1
    assert summary.imported == []
    assert summary.missing_lines["Legacy"] == ["41a9625cec8cf0f0"]
