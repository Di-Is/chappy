"""Organize-mode application ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from chappy.application.analysis_artifacts import (
    GlobalAnalysisMutationProjectPort,
    RegionLocalMutationProjectPort,
)
from chappy.application.structure import AtomicStructureProjectPort

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextlib import AbstractContextManager

    from chappy.application.history import (
        AbsorptionLineSnapshot,
        OrganizeDeleteModelHistorySnapshot,
        OrganizeMoveHistoryPayload,
        OrganizeStructureStateSnapshot,
        OrganizeUnlinkHistoryPayload,
    )
    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.resolution import ResolutionState


class OrganizeProjectPort(AtomicStructureProjectPort, RegionLocalMutationProjectPort, Protocol):
    """Minimal project operations required by organize use cases."""

    def find_absorption_line(self, line_id: str) -> AbsorptionLine | None:
        """Return an absorption line by ID."""
        ...

    def find_absorption_region(self, region_id: str) -> AbsorptionRegion | None:
        """Return an absorption region by ID."""
        ...

    def expand_multiplet_line_ids(self, seed_ids: Sequence[str]) -> list[str]:
        """Expand line IDs with multiplet companions."""
        ...

    def move_absorption_lines(
        self, line_ids: list[str], *, target_region_id: str | None
    ) -> str | None:
        """Move lines into a target region."""
        ...

    def merge_absorption_regions(self, region_ids: list[str]) -> AbsorptionRegion | None:
        """Merge regions into the primary selected region."""
        ...

    def unlink_absorption_line_system(self, line_id: str) -> tuple[str, ...]:
        """Unlink one materialized multiplet system and return changed line IDs."""
        ...

    def remove_absorption_region(self, region_id: str, *, delete_models: bool = True) -> int:
        """Remove an absorption region."""
        ...

    def remove_absorption_lines_with_multiplet(
        self, line_ids: list[str], *, delete_models: bool = True
    ) -> int:
        """Remove selected lines and multiplet companions."""
        ...


class ResolutionProjectPort(GlobalAnalysisMutationProjectPort, Protocol):
    """Minimal project operation required by resolution use cases."""

    @property
    def resolution_state(self) -> ResolutionState:
        """Return the current instrumental resolution state."""
        ...

    def set_resolution(self, value: float, enabled: bool) -> None:
        """Apply resolution state to the project."""
        ...


@runtime_checkable
class OrganizeMoveHistoryRecorder(Protocol):
    """History recorder interface needed by atomic organize moves."""

    def record_group_move_systems(self, payload: OrganizeMoveHistoryPayload) -> None:
        """Record moved organize systems."""
        ...

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return the history-only rollback scope required by forward moves."""
        ...


@runtime_checkable
class OrganizeHistoryRecorder(OrganizeMoveHistoryRecorder, Protocol):
    """History recorder interface needed by all organize operations."""

    def record_group_split(
        self,
        expanded_line_ids: tuple[str, ...],
        source_region_id: str,
        new_region_id: str,
        before: OrganizeStructureStateSnapshot,
        after: OrganizeStructureStateSnapshot,
    ) -> None:
        """Record a organize split operation."""
        ...

    def record_group_merge(
        self,
        primary_region_id: str,
        secondary_region_ids: tuple[str, ...],
        before: OrganizeStructureStateSnapshot,
        after: OrganizeStructureStateSnapshot,
    ) -> None:
        """Record a organize merge operation."""
        ...

    def record_group_delete(
        self,
        target_region_ids: tuple[str, ...],
        target_line_ids: tuple[str, ...],
        deleted_lines: tuple[AbsorptionLineSnapshot, ...],
        before: OrganizeStructureStateSnapshot,
        after: OrganizeStructureStateSnapshot,
        deleted_model_history: OrganizeDeleteModelHistorySnapshot | None,
    ) -> None:
        """Record a organize delete operation."""
        ...

    def record_group_unlink(self, payload: OrganizeUnlinkHistoryPayload) -> None:
        """Record one materialized line-system unlink operation."""
        ...


@runtime_checkable
class ResolutionChangeNotifier(Protocol):
    """Notifier interface for consumers that react to resolution changes."""

    def notify_resolution_changed(self) -> None:
        """Notify that the current project resolution changed."""
        ...


__all__ = [
    "OrganizeHistoryRecorder",
    "OrganizeMoveHistoryRecorder",
    "OrganizeProjectPort",
    "ResolutionChangeNotifier",
    "ResolutionProjectPort",
]
