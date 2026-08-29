"""Organize-mode application result models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.application.analysis_artifacts import AnalysisMutationImpact
    from chappy.core.absorption.models import AbsorptionRegion


@dataclass(frozen=True, slots=True)
class OrganizeMoveResult:
    """Result of moving absorption lines between organize regions."""

    destination_id: str
    moved_system_count: int
    destination_region: AbsorptionRegion | None


@dataclass(frozen=True, slots=True)
class OrganizeMergeResult:
    """Result of merging organize regions."""

    merged_region: AbsorptionRegion


@dataclass(frozen=True, slots=True)
class OrganizeSplitResult:
    """Result of splitting selected lines into a new organize region."""

    new_region: AbsorptionRegion | None


@dataclass(frozen=True, slots=True)
class OrganizeDeleteResult:
    """Result of deleting organize regions or systems."""

    groups_removed: int
    systems_removed: int


@dataclass(frozen=True, slots=True)
class OrganizeUnlinkResult:
    """Result of unlinking one materialized absorption-line system."""

    unlinked_line_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolutionUpdateResult:
    """Result of applying a spectral resolution value."""

    value: float
    enabled: bool
    impact: AnalysisMutationImpact


__all__ = [
    "OrganizeDeleteResult",
    "OrganizeMergeResult",
    "OrganizeMoveResult",
    "OrganizeSplitResult",
    "OrganizeUnlinkResult",
    "ResolutionUpdateResult",
]
