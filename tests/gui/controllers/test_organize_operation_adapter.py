"""Tests for organize operation mutation adapter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from chappy.application.history import (
    AbsorptionLineSnapshot,
    LineRegionAssignment,
    OrganizeDeleteModelHistorySnapshot,
    OrganizeMoveHistoryPayload,
    OrganizeStructureStateSnapshot,
    OrganizeUnlinkHistoryPayload,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.application.organize import OrganizeOperationUseCase
from chappy.gui.modes.analysis.overview.adapters import OrganizeOperationAdapter


@dataclass
class _RecordingHistory:
    """Record organize history calls."""

    move_calls: list[OrganizeMoveHistoryPayload] = field(default_factory=list)
    split_calls: list[dict[str, object]] = field(default_factory=list)
    merge_calls: list[dict[str, object]] = field(default_factory=list)
    delete_calls: list[dict[str, object]] = field(default_factory=list)
    unlink_calls: list[OrganizeUnlinkHistoryPayload] = field(default_factory=list)

    def record_group_move_systems(self, payload: OrganizeMoveHistoryPayload) -> None:
        """Record moved organize systems."""
        self.move_calls.append(payload)

    @contextmanager
    def atomic_recording(self) -> Iterator[None]:
        """Provide an atomic history scope for move recording."""
        yield

    def record_group_split(
        self,
        expanded_line_ids: tuple[str, ...],
        source_region_id: str,
        new_region_id: str,
        before: OrganizeStructureStateSnapshot,
        after: OrganizeStructureStateSnapshot,
    ) -> None:
        """Record a organize split operation."""
        self.split_calls.append(
            {
                "expanded_line_ids": expanded_line_ids,
                "source_region_id": source_region_id,
                "new_region_id": new_region_id,
                "before": before,
                "after": after,
            }
        )

    def record_group_merge(
        self,
        primary_region_id: str,
        secondary_region_ids: tuple[str, ...],
        before: OrganizeStructureStateSnapshot,
        after: OrganizeStructureStateSnapshot,
    ) -> None:
        """Record a organize merge operation."""
        self.merge_calls.append(
            {
                "primary_region_id": primary_region_id,
                "secondary_region_ids": secondary_region_ids,
                "before": before,
                "after": after,
            }
        )

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
        self.delete_calls.append(
            {
                "target_region_ids": target_region_ids,
                "target_line_ids": target_line_ids,
                "deleted_lines": deleted_lines,
                "before": before,
                "after": after,
                "deleted_model_history": deleted_model_history,
            }
        )

    def record_group_unlink(self, payload: OrganizeUnlinkHistoryPayload) -> None:
        """Record one exact line-system unlink."""
        self.unlink_calls.append(payload)


def _line(line_id: str, region_id: str, *, related_ids: list[str] | None = None) -> AbsorptionLine:
    """Create an absorption line assigned to a region."""
    return AbsorptionLine(
        line_id=line_id,
        species="Mg II",
        rest_wavelength=2796.35,
        center_z=1.0,
        window_kms=150.0,
        multiplet_label="Mg II",
        transition_name="Mg II 2796",
        oscillator_strength=0.6,
        gamma_value=1.0e8,
        region_id=region_id,
        multiplet_ids=list(related_ids or []),
    )


def _add_region(project: SpectroscopyProject, region_id: str, line_ids: list[str]) -> None:
    """Add a region and matching lines to a project."""
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=list(line_ids)
    )
    for line_id in line_ids:
        project.absorption_lines[line_id] = _line(line_id, region_id)


def test_move_lines_mutates_project_and_records_history() -> None:
    """Move operation records source assignments outside DockLayoutCoordinator."""
    project = SpectroscopyProject()
    _add_region(project, "source", ["line_1"])
    _add_region(project, "target", [])
    history = _RecordingHistory()

    result = OrganizeOperationAdapter(OrganizeOperationUseCase()).move_lines(
        project, line_ids=["line_1"], target_region_id="target", history_recorder=history
    )

    assert result is not None
    assert result.destination_id == "target"
    assert result.moved_system_count == 1
    assert "source" not in project.absorption_regions
    assert project.absorption_regions["target"].line_ids == ["line_1"]
    assert history.move_calls[0].source_assignments == (
        LineRegionAssignment(line_id="line_1", region_id="source"),
    )


def test_delete_selection_expands_multiplet_and_records_snapshots() -> None:
    """Delete operation captures multiplet links before mutation."""
    project = SpectroscopyProject()
    project.absorption_regions["region"] = AbsorptionRegion(
        region_id="region", line_ids=["blue", "red"]
    )
    project.absorption_lines["blue"] = _line("blue", "region", related_ids=["red"])
    project.absorption_lines["red"] = _line("red", "region", related_ids=["blue"])
    history = _RecordingHistory()

    result = OrganizeOperationAdapter(OrganizeOperationUseCase()).delete_selection(
        project, group_ids=[], system_ids=["blue"], history_recorder=history
    )

    assert result is not None
    assert result.groups_removed == 0
    assert result.systems_removed == 2
    assert project.absorption_lines == {}
    assert history.delete_calls[0]["target_line_ids"] == ("blue", "red")
    deleted_lines = history.delete_calls[0]["deleted_lines"]
    assert isinstance(deleted_lines, tuple)
    assert tuple(snapshot.multiplet_ids for snapshot in deleted_lines) == (("red",), ("blue",))


def test_unlink_line_system_routes_exact_history_payload() -> None:
    """Unlink adapter delegates to the forward use case and typed history recorder."""
    project = SpectroscopyProject()
    project.absorption_regions["region"] = AbsorptionRegion(
        region_id="region", line_ids=["blue", "red"]
    )
    project.absorption_lines["blue"] = _line("blue", "region", related_ids=["red"])
    project.absorption_lines["red"] = _line("red", "region", related_ids=["blue"])
    history = _RecordingHistory()

    result = OrganizeOperationAdapter(OrganizeOperationUseCase()).unlink_line_system(
        project, line_id="blue", history_recorder=history
    )

    assert result is not None
    assert result.unlinked_line_ids == ("blue", "red")
    assert project.absorption_lines["blue"].multiplet_ids == []
    assert project.absorption_lines["red"].multiplet_ids == []
    assert len(history.unlink_calls) == 1
    assert history.unlink_calls[0].line_ids == ("blue", "red")
