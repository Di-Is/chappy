"""Tests for typed scientific structure mutation outcomes."""

from __future__ import annotations

import pytest

from chappy.application.structure import (
    StructureInvalidationScope,
    StructureMutationOutcome,
    StructureMutationResult,
    StructureRegionDelta,
)


def test_structure_region_delta_normalizes_each_identity_set() -> None:
    """Region identities should keep first-seen order without duplicates."""
    delta = StructureRegionDelta(
        invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
        affected_surviving_region_ids=("b", "a", "b"),
        created_region_ids=("new", "new"),
        removed_region_ids=("old", "old"),
    )

    assert delta.affected_surviving_region_ids == ("b", "a")
    assert delta.created_region_ids == ("new",)
    assert delta.removed_region_ids == ("old",)


@pytest.mark.parametrize(
    ("affected", "created", "removed"),
    [
        (("shared",), ("shared",), ()),
        (("shared",), (), ("shared",)),
        ((), ("shared",), ("shared",)),
    ],
)
def test_structure_region_delta_rejects_overlapping_sets(
    affected: tuple[str, ...], created: tuple[str, ...], removed: tuple[str, ...]
) -> None:
    """One region cannot have two topology roles in the same transition."""
    with pytest.raises(ValueError, match="must be disjoint"):
        StructureRegionDelta(
            invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
            affected_surviving_region_ids=affected,
            created_region_ids=created,
            removed_region_ids=removed,
        )


def test_structure_mutation_result_requires_delta_only_for_change() -> None:
    """Changed and no-change results should be mutually exclusive typed states."""
    delta = StructureRegionDelta(
        invalidation_scope=StructureInvalidationScope.LOCAL_SURVIVORS,
        affected_surviving_region_ids=("region",),
    )
    changed = StructureMutationResult.changed_result("value", delta)
    no_change = StructureMutationResult[str].no_change()

    assert changed.changed
    assert changed.value == "value"
    assert changed.delta is delta
    assert no_change.outcome is StructureMutationOutcome.NO_CHANGE
    assert not no_change.changed

    with pytest.raises(ValueError, match="requires a region delta"):
        StructureMutationResult[str](outcome=StructureMutationOutcome.CHANGED)
    with pytest.raises(ValueError, match="cannot carry"):
        StructureMutationResult(
            outcome=StructureMutationOutcome.NO_CHANGE, value="value", delta=delta
        )
