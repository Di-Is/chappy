"""Tests for declaration-driven absorption-line link materialization."""

from __future__ import annotations

from chappy.core.absorption.models import AbsorptionLine
from chappy.core.absorption.multiplet_service import setup_multiplet_cross_references


def _line(line_id: str, center_z: float = 1.0) -> AbsorptionLine:
    """Build a minimal absorption line."""
    return AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1200.0,
        center_z=center_z,
        window_kms=100.0,
        multiplet_label="",
        transition_name=line_id,
        oscillator_strength=0.1,
        gamma_value=1.0,
    )


def test_setup_materializes_clique_from_declared_group() -> None:
    """Every member references every other declared member."""
    lines = [_line("b"), _line("a"), _line("c")]

    setup_multiplet_cross_references({"group": lines})

    assert lines[0].multiplet_ids == ["a", "c"]
    assert lines[1].multiplet_ids == ["b", "c"]
    assert lines[2].multiplet_ids == ["a", "b"]


def test_setup_ignores_empty_and_single_member_groups() -> None:
    """No structural links are created without at least two members."""
    single = _line("single")
    ignored = _line("ignored")

    setup_multiplet_cross_references({"": [single], "one": [ignored]})

    assert single.multiplet_ids == []
    assert ignored.multiplet_ids == []


def test_setup_separates_keys_and_redshift_buckets() -> None:
    """Different declarations and z buckets remain independent."""
    same_key_other_z = _line("other-z", center_z=1.01)
    first = _line("first")
    second = _line("second")
    other_group = _line("other-group")

    setup_multiplet_cross_references(
        {"group-a": [first, second, same_key_other_z], "group-b": [other_group]}
    )

    assert first.multiplet_ids == ["second"]
    assert second.multiplet_ids == ["first"]
    assert same_key_other_z.multiplet_ids == []
    assert other_group.multiplet_ids == []
