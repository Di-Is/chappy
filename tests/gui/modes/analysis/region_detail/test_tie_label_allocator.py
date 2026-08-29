"""Tests for the session-scoped parameter tie set label allocator."""

from __future__ import annotations

from chappy.gui.modes.analysis.region_detail.tree.tie_label_allocator import (
    OptimizeTieLabelAllocator,
)


def test_label_for_assigns_sequentially_in_first_seen_order() -> None:
    """Labels should be assigned A, B, C, ... in first-seen order."""
    allocator = OptimizeTieLabelAllocator()

    assert allocator.label_for("tie-1") == "A"
    assert allocator.label_for("tie-2") == "B"
    assert allocator.label_for("tie-3") == "C"


def test_label_for_is_stable_within_session() -> None:
    """Repeated lookups for the same tie id should return the same label."""
    allocator = OptimizeTieLabelAllocator()

    first = allocator.label_for("tie-1")
    allocator.label_for("tie-2")
    second = allocator.label_for("tie-1")

    assert first == second == "A"


def test_label_for_rolls_over_from_z_to_aa() -> None:
    """The 27th assigned tie id should roll over to AA."""
    allocator = OptimizeTieLabelAllocator()

    labels = [allocator.label_for(f"tie-{index}") for index in range(53)]

    assert labels[:26] == [chr(ord("A") + index) for index in range(26)]
    assert labels[25] == "Z"
    assert labels[26] == "AA"
    assert labels[27] == "AB"
    assert labels[51] == "AZ"
    assert labels[52] == "BA"


def test_assign_all_preserves_iteration_order_and_existing_labels() -> None:
    """assign_all should assign new ids in order while keeping existing labels."""
    allocator = OptimizeTieLabelAllocator()
    allocator.label_for("tie-2")

    allocator.assign_all(["tie-1", "tie-2", "tie-3"])

    assert allocator.label_for("tie-2") == "A"
    assert allocator.label_for("tie-1") == "B"
    assert allocator.label_for("tie-3") == "C"


def test_reset_clears_all_assigned_labels() -> None:
    """reset should clear assignments so a new session restarts from A."""
    allocator = OptimizeTieLabelAllocator()
    allocator.label_for("tie-1")
    allocator.label_for("tie-2")

    allocator.reset()

    assert allocator.label_for("tie-2") == "A"


def test_reload_with_same_iteration_order_reproduces_same_labels() -> None:
    """A project reload iterating tie sets in the same order should yield identical labels."""
    tie_ids = ["tie-a", "tie-b", "tie-c"]

    first_session = OptimizeTieLabelAllocator()
    first_session.assign_all(tie_ids)
    first_labels = [first_session.label_for(tie_id) for tie_id in tie_ids]

    second_session = OptimizeTieLabelAllocator()
    second_session.reset()
    second_session.assign_all(tie_ids)
    second_labels = [second_session.label_for(tie_id) for tie_id in tie_ids]

    assert first_labels == second_labels == ["A", "B", "C"]


def test_index_for_returns_zero_based_assignment_order() -> None:
    """index_for should mirror the 0-based order used to select accent colors."""
    allocator = OptimizeTieLabelAllocator()

    assert allocator.index_for("tie-1") == 0
    assert allocator.index_for("tie-2") == 1
    assert allocator.index_for("tie-1") == 0
