"""Tests for pure preset tie-group validation and suggestions."""

from __future__ import annotations

from chappy.application.presets import suggest_preset_tie_groups, validate_preset_tie_group_members
from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.core.presets import Preset, PresetTieGroup, TieGroupIssue


def _line(identifier: str, species: str, multiplet_id: str = "") -> AtomicLine:
    """Build a compact atomic line fixture."""
    return AtomicLine(
        line_identifier=identifier,
        species=species,
        wavelength_angstrom=1200.0 + len(identifier),
        oscillator_strength=0.1,
        gamma_value=1.0,
        multiplet_id=multiplet_id,
    )


def _preset() -> tuple[Preset, AtomicLineData]:
    """Build a preset containing two DB multiplets and one single line."""
    atomic_data = AtomicLineData(
        [
            _line("c-1", "C IV", "civ"),
            _line("c-2", "C IV", "civ"),
            _line("si-1", "Si IV", "si"),
            _line("si-2", "Si IV", "si"),
            _line("single", "H I"),
        ]
    )
    preset = Preset(
        id="preset",
        name="Preset",
        source="custom",
        line_ids=["c-1", "c-2", "si-1", "si-2", "single"],
    )
    return preset, atomic_data


def test_suggestions_are_deterministic_and_exclude_grouped_lines() -> None:
    """Suggestions contain only ungrouped preset lines in preset order."""
    preset, atomic_data = _preset()
    preset.tie_groups = [PresetTieGroup(uid="civ-group", line_ids=("c-1", "c-2"))]

    suggestions = suggest_preset_tie_groups(preset, atomic_data)

    assert [(item.multiplet_id, item.line_ids) for item in suggestions] == [
        ("si", ("si-1", "si-2"))
    ]


def test_suggestions_split_same_multiplet_when_species_differs() -> None:
    """Species is part of the suggestion key as a malformed-data guard."""
    preset, atomic_data = _preset()
    mixed = _line("mixed", "H I", "civ")
    atomic_data = AtomicLineData([*atomic_data.lines, mixed])
    preset.line_ids.append(mixed.line_id)

    suggestions = suggest_preset_tie_groups(preset, atomic_data)

    assert {(item.multiplet_id, item.species) for item in suggestions} == {
        ("civ", "C IV"),
        ("si", "Si IV"),
    }
    assert all(mixed.line_id not in item.line_ids for item in suggestions)


def test_validation_reports_deterministic_issues() -> None:
    """Validation rejects membership, species, and duplicate-group violations."""
    preset, atomic_data = _preset()

    assert (
        validate_preset_tie_group_members(preset, ["c-1"], atomic_data)
        == TieGroupIssue.TOO_FEW_LINES
    )
    assert (
        validate_preset_tie_group_members(preset, ["c-1", "outside"], atomic_data)
        == TieGroupIssue.LINE_NOT_IN_PRESET
    )
    assert (
        validate_preset_tie_group_members(preset, ["c-1", "si-1"], atomic_data)
        == TieGroupIssue.MIXED_SPECIES
    )

    preset.tie_groups = [PresetTieGroup(uid="civ-group", line_ids=("c-1", "c-2"))]
    assert (
        validate_preset_tie_group_members(preset, ["c-1", "c-2"], atomic_data)
        == TieGroupIssue.ALREADY_GROUPED
    )
    assert (
        validate_preset_tie_group_members(
            preset, ["c-1", "c-2"], atomic_data, editing_group_uid="civ-group"
        )
        is None
    )


def test_validation_reports_unknown_line_in_preset() -> None:
    """A stale line reference is reported separately from preset membership."""
    preset, atomic_data = _preset()
    preset.line_ids.append("stale")

    result = validate_preset_tie_group_members(preset, ["c-1", "stale"], atomic_data)

    assert result == TieGroupIssue.UNKNOWN_LINE
