"""Tests for declarative preset tie-group behavior."""

from __future__ import annotations

import pytest

from chappy.core.atomic_data import AtomicLine, AtomicLineData
from chappy.core.presets import Preset, PresetStore, PresetTieGroup


def _line(identifier: str, species: str, wavelength: float) -> AtomicLine:
    return AtomicLine(
        line_identifier=identifier,
        species=species,
        wavelength_angstrom=wavelength,
        oscillator_strength=0.1,
        gamma_value=1.0,
    )


@pytest.fixture
def atomic_data() -> AtomicLineData:
    return AtomicLineData(
        [
            _line("a", "C IV", 1548.2),
            _line("b", "C IV", 1550.8),
            _line("c", "Si IV", 1393.8),
            _line("f", "Si IV", 1402.8),
            _line("d", "C IV", 1551.0),
            _line("e", "C IV", 1551.5),
        ]
    )


def _store(atomic_data: AtomicLineData) -> PresetStore:
    return PresetStore(atomic_data, translate=lambda text: text)


def test_group_local_invariants_are_strict() -> None:
    with pytest.raises(ValueError, match="uid"):
        PresetTieGroup(uid=" ", line_ids=("a", "b"))
    with pytest.raises(ValueError, match="at least two"):
        PresetTieGroup(uid="group", line_ids=("a",))
    with pytest.raises(ValueError, match="unique"):
        PresetTieGroup(uid="group", line_ids=("a", "a"))


def test_preset_validation_rejects_membership_overlap_and_species(
    atomic_data: AtomicLineData,
) -> None:
    preset = Preset(
        id="preset",
        name="Preset",
        source="custom",
        line_ids=["a", "b", "c"],
        tie_groups=[PresetTieGroup(uid="one", line_ids=("a", "b"))],
    )
    preset.validate_tie_groups(atomic_data)

    preset.tie_groups.append(PresetTieGroup(uid="two", line_ids=("b", "c")))
    with pytest.raises(ValueError, match="multiple"):
        preset.validate_tie_groups(atomic_data)

    preset.tie_groups = [PresetTieGroup(uid="mixed", line_ids=("a", "c"))]
    with pytest.raises(ValueError, match="same ion"):
        preset.validate_tie_groups(atomic_data)


def test_tie_group_edit_operations_are_atomic_and_sync_line_removal(
    atomic_data: AtomicLineData,
) -> None:
    store = _store(atomic_data)
    preset = store.create_custom_preset("Custom", line_ids=["a", "b", "c", "d"])

    group = store.add_tie_group(preset.id, ["a", "b"])
    assert group.line_ids == ("a", "b")
    before = store.get_preset(preset.id)
    assert before is not None

    with pytest.raises(ValueError, match="same ion"):
        store.replace_tie_group_members(preset.id, group.uid, ["a", "c"])
    unchanged = store.get_preset(preset.id)
    assert unchanged is not None
    assert unchanged.tie_groups == [group]
    assert unchanged.updated_at == before.updated_at

    replacement = store.replace_tie_group_members(preset.id, group.uid, ["a", "d"])
    assert replacement.uid != group.uid
    store.remove_lines(preset.id, ["d"])
    after_removal = store.get_preset(preset.id)
    assert after_removal is not None
    assert after_removal.tie_groups == []


def test_replacing_group_members_reissues_transient_identity(atomic_data: AtomicLineData) -> None:
    """Stale candidates must not share a key with a changed declaration."""
    store = _store(atomic_data)
    preset = store.create_custom_preset("Custom", line_ids=["a", "b", "c", "f"])
    original = store.add_tie_group(preset.id, ["a", "b"])

    replacement = store.replace_tie_group_members(preset.id, original.uid, ["c", "f"])

    assert replacement.uid != original.uid


def test_duplicate_preserves_metadata_and_groups_independently(
    atomic_data: AtomicLineData,
) -> None:
    store = _store(atomic_data)
    source = store.create_custom_preset(
        "Custom", line_ids=["a", "b"], baseline_id="b", description="details"
    )
    group = store.add_tie_group(source.id, ["a", "b"])

    duplicate = store.duplicate_preset(source.id)
    assert duplicate.id != source.id
    assert duplicate.line_ids == source.line_ids
    assert duplicate.baseline_id == "b"
    assert duplicate.description == "details"
    assert duplicate.tie_groups == [group]

    store.remove_tie_group(duplicate.id, group.uid)
    assert store.get_preset(source.id).tie_groups == [group]  # type: ignore[union-attr]


def test_external_groups_are_normalized_with_first_group_precedence(
    atomic_data: AtomicLineData,
) -> None:
    store = _store(atomic_data)
    preset = Preset(
        id="custom",
        name="Custom",
        source="custom",
        line_ids=["a", "b", "c", "d"],
        tie_groups=[
            PresetTieGroup(uid="first", line_ids=("a", "b")),
            PresetTieGroup(uid="second", line_ids=("b", "c", "d")),
        ],
    )
    store.replace_custom_presets([preset])
    loaded = store.get_preset("custom")
    assert loaded is not None
    assert loaded.tie_groups == [PresetTieGroup(uid="first", line_ids=("a", "b"))]


def test_builtin_preset_structural_edits_are_rejected(atomic_data: AtomicLineData) -> None:
    """Built-in presets remain read-only for structural preset mutation APIs."""
    store = _store(atomic_data)
    builtin = store.get_preset("builtin:lyman")
    if builtin is None:
        pytest.skip("The test fixture does not contain bundled lines")

    with pytest.raises(PermissionError):
        store.add_tie_group(builtin.id, builtin.line_ids[:2])


def test_set_baseline_succeeds_on_builtin_preset() -> None:
    """Baseline selection is session usage state, allowed even on built-in presets."""
    lyman_ids = (
        "8cd0394ff25e72e7",
        "cd0f85d159976946",
        "2feafb6deab92064",
        "35815e9743604328",
        "9f1f1a3dae473067",
    )
    lines = [_line(line_id, "H I", 1215.0 + index) for index, line_id in enumerate(lyman_ids)]
    store = _store(AtomicLineData(lines))

    builtin = store.get_preset("builtin:lyman")
    assert builtin is not None
    assert len(builtin.line_ids) >= 2

    other_line_id = next(line_id for line_id in builtin.line_ids if line_id != builtin.baseline_id)

    store.set_baseline(builtin.id, other_line_id)

    updated = store.get_preset(builtin.id)
    assert updated is not None
    assert updated.baseline_id == other_line_id


def test_add_lines_with_tie_groups_extends_overlapping_group(atomic_data: AtomicLineData) -> None:
    """A proposal overlapping exactly one existing group extends it in place."""
    store = _store(atomic_data)
    preset = store.create_custom_preset("Custom", line_ids=["a", "b"])
    group = store.add_tie_group(preset.id, ["a", "b"])

    added = store.add_lines_with_tie_groups(preset.id, ["d"], [["a", "b", "d"]])

    assert added == ["d"]
    updated = store.get_preset(preset.id)
    assert updated is not None
    assert updated.line_ids == ["a", "b", "d"]
    assert [item.line_ids for item in updated.tie_groups] == [("a", "b", "d")]
    assert updated.tie_groups[0].uid != group.uid


def test_add_lines_with_tie_groups_skips_proposal_spanning_two_groups(
    atomic_data: AtomicLineData,
) -> None:
    """A proposal overlapping two existing groups is skipped, groups unchanged."""
    store = _store(atomic_data)
    preset = store.create_custom_preset("Custom", line_ids=["a", "b", "d", "e"])
    group_one = store.add_tie_group(preset.id, ["a", "b"])
    group_two = store.add_tie_group(preset.id, ["d", "e"])

    added = store.add_lines_with_tie_groups(preset.id, [], [["a", "d"]])

    assert added == []
    updated = store.get_preset(preset.id)
    assert updated is not None
    assert updated.tie_groups == [group_one, group_two]


def test_add_lines_with_tie_groups_creates_new_group_without_overlap(
    atomic_data: AtomicLineData,
) -> None:
    """A proposal that overlaps no existing group is created as a new group."""
    store = _store(atomic_data)
    preset = store.create_custom_preset("Custom", line_ids=["a", "b"])

    added = store.add_lines_with_tie_groups(preset.id, [], [["a", "b"]])

    assert added == []
    updated = store.get_preset(preset.id)
    assert updated is not None
    assert len(updated.tie_groups) == 1
    assert updated.tie_groups[0].line_ids == ("a", "b")


def test_add_lines_with_tie_groups_never_fails_line_addition(atomic_data: AtomicLineData) -> None:
    """Line addition succeeds even when every proposed group must be skipped."""
    store = _store(atomic_data)
    preset = store.create_custom_preset("Custom", line_ids=["a", "b", "d", "e"])
    store.add_tie_group(preset.id, ["a", "b"])
    store.add_tie_group(preset.id, ["d", "e"])

    added = store.add_lines_with_tie_groups(preset.id, ["c"], [["a", "d"]])

    assert added == ["c"]
    updated = store.get_preset(preset.id)
    assert updated is not None
    assert "c" in updated.line_ids
