"""Pure domain services for multiplet cross-references and expansion."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from chappy.core.absorption.models import AbsorptionLine


def materialized_tie_group_key(line_ids: Iterable[str]) -> str:
    """Derive the opaque slice-grouping key for one materialized linked group."""
    return f"materialized:{min(line_ids)}"


def setup_multiplet_cross_references(
    grouped_lines: Mapping[str, Sequence[AbsorptionLine]], z_tolerance: float = 0.001
) -> None:
    """Materialize cross-references for candidates in declared tie groups.

    Lines are grouped by the transient declaration key and center-z bucket. The
    atomic database is intentionally not consulted here: declarations are the
    only source that can create structural links.

    Args:
        grouped_lines: Mapping from declaration key to absorption lines.
        z_tolerance: Tolerance for comparing center_z values (default 0.001).
    """
    # Group absorption lines by (declarative tie-group key, rounded_z).
    multiplet_z_groups: dict[tuple[str, float], list[AbsorptionLine]] = {}

    for tie_group_key, absorption_lines in grouped_lines.items():
        if not tie_group_key:
            continue

        for absorption_line in absorption_lines:
            # Round z to bucket for grouping (handles floating point comparison)
            z_bucket = round(absorption_line.center_z / z_tolerance) * z_tolerance
            key = (tie_group_key, z_bucket)
            multiplet_z_groups.setdefault(key, []).append(absorption_line)

    for group in multiplet_z_groups.values():
        if len(group) < 2:
            # Single line in group, no cross-references needed
            continue

        # Collect all line IDs in the group
        group_line_ids = {line.line_id for line in group}

        # Set each line's multiplet_ids to reference the others
        for line in group:
            other_ids = group_line_ids - {line.line_id}
            # Clear existing and set new cross-references
            line.multiplet_ids.clear()
            line.multiplet_ids.extend(sorted(other_ids))


def expand_multiplet_lines(
    lines_by_id: Mapping[str, AbsorptionLine], seed_ids: Sequence[str]
) -> list[str]:
    """Expand seed line IDs to include all directly cross-referenced multiplet companions.

    Args:
        lines_by_id: Absorption lines keyed by line ID.
        seed_ids: Initial line IDs to expand.

    Returns:
        Expanded line IDs including multiplet companions, in traversal order.
    """
    expanded: list[str] = []
    seen: set[str] = set()
    queue = deque(seed_ids)

    while queue:
        line_id = queue.popleft()
        if line_id in seen:
            continue
        seen.add(line_id)
        expanded.append(line_id)

        line = lines_by_id.get(line_id)
        if line is None:
            continue

        direct_refs = [raw for raw in line.multiplet_ids if raw in lines_by_id and raw not in seen]
        if direct_refs:
            queue.extend(direct_refs)

    return expanded
