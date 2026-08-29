"""Organize-mode operation adapter for GUI controllers."""

from __future__ import annotations

from chappy.application.organize import (
    OrganizeDeleteResult,
    OrganizeHistoryRecorder,
    OrganizeMergeResult,
    OrganizeMoveResult,
    OrganizeOperationUseCase,
    OrganizeProjectPort,
    OrganizeSplitResult,
    OrganizeUnlinkResult,
)


class OrganizeOperationAdapter:
    """Delegate organize project operations to application use cases."""

    def __init__(self, use_case: OrganizeOperationUseCase) -> None:
        """Initialize the adapter.

        Args:
            use_case: Organize operation use case.
        """
        self._use_case = use_case

    def move_lines(
        self,
        project: OrganizeProjectPort,
        *,
        line_ids: list[str],
        target_region_id: str | None,
        history_recorder: OrganizeHistoryRecorder | None,
    ) -> OrganizeMoveResult | None:
        """Move selected lines to a target region."""
        return self._use_case.move_lines(
            project,
            line_ids=line_ids,
            target_region_id=target_region_id,
            history_recorder=history_recorder,
        )

    def merge_regions(
        self,
        project: OrganizeProjectPort,
        *,
        group_ids: list[str],
        history_recorder: OrganizeHistoryRecorder | None,
    ) -> OrganizeMergeResult | None:
        """Merge selected regions into the primary region."""
        return self._use_case.merge_regions(
            project, group_ids=group_ids, history_recorder=history_recorder
        )

    def split_lines(
        self,
        project: OrganizeProjectPort,
        *,
        system_ids: list[str],
        history_recorder: OrganizeHistoryRecorder | None,
    ) -> OrganizeSplitResult | None:
        """Split selected lines into a new region."""
        return self._use_case.split_lines(
            project, system_ids=system_ids, history_recorder=history_recorder
        )

    def delete_selection(
        self,
        project: OrganizeProjectPort,
        *,
        group_ids: list[str],
        system_ids: list[str],
        history_recorder: OrganizeHistoryRecorder | None,
    ) -> OrganizeDeleteResult | None:
        """Delete selected regions and systems."""
        return self._use_case.delete_selection(
            project, group_ids=group_ids, system_ids=system_ids, history_recorder=history_recorder
        )

    def unlink_line_system(
        self,
        project: OrganizeProjectPort,
        *,
        line_id: str,
        history_recorder: OrganizeHistoryRecorder | None,
    ) -> OrganizeUnlinkResult | None:
        """Remove the materialized links for one selected line system."""
        return self._use_case.unlink_line_system(
            project, line_id=line_id, history_recorder=history_recorder
        )


__all__ = [
    "OrganizeDeleteResult",
    "OrganizeHistoryRecorder",
    "OrganizeMergeResult",
    "OrganizeMoveResult",
    "OrganizeOperationAdapter",
    "OrganizeProjectPort",
    "OrganizeSplitResult",
    "OrganizeUnlinkResult",
]
