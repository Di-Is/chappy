"""Pure validation and suggestion helpers for preset tie groups."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.presets import evaluate_tie_group_issue

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chappy.core.atomic_data import AtomicLineData, LineIdentifier
    from chappy.core.presets import Preset, TieGroupIssue


@dataclass(frozen=True, slots=True)
class PresetTieGroupSuggestion:
    """A DB multiplet that can be explicitly declared as a preset group."""

    multiplet_id: str
    species: str
    line_ids: tuple[LineIdentifier, ...]


def validate_preset_tie_group_members(
    preset: Preset,
    line_ids: Sequence[LineIdentifier],
    atomic_data: AtomicLineData,
    *,
    editing_group_uid: str | None = None,
) -> TieGroupIssue | None:
    """Validate one new or edited group; return the first issue or None when valid."""
    other_groups = [group for group in preset.tie_groups if group.uid != editing_group_uid]
    return evaluate_tie_group_issue(
        None,
        line_ids,
        preset_line_ids=preset.line_ids,
        atomic_data=atomic_data,
        other_groups=other_groups,
    )


def suggest_preset_tie_groups(
    preset: Preset, atomic_data: AtomicLineData
) -> tuple[PresetTieGroupSuggestion, ...]:
    """Suggest explicit groups from ungrouped lines sharing a DB multiplet."""
    grouped_line_ids = {line_id for group in preset.tie_groups for line_id in group.line_ids}
    candidates: dict[tuple[str, str], list[LineIdentifier]] = defaultdict(list)
    for line_id in preset.line_ids:
        if line_id in grouped_line_ids:
            continue
        line = atomic_data.get_line_by_id(line_id)
        if line is None or not line.multiplet_id:
            continue
        candidates[(line.multiplet_id, line.species)].append(line_id)

    suggestions = [
        PresetTieGroupSuggestion(
            multiplet_id=multiplet_id, species=species, line_ids=tuple(line_ids)
        )
        for (multiplet_id, species), line_ids in candidates.items()
        if len(line_ids) >= 2
    ]
    return tuple(suggestions)


__all__ = [
    "PresetTieGroupSuggestion",
    "suggest_preset_tie_groups",
    "validate_preset_tie_group_members",
]
