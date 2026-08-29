"""Tests for typed identify history commands."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from chappy.application.history import (
    AbsorptionLineSnapshot,
    AbsorptionRegionSnapshot,
    ChangeSet,
    HistoryCommandContext,
    IdentifyAddCandidateCommand,
    IdentifyClearCandidatesCommand,
    IdentifyRegisterSelectedCommand,
    IdentifyRemoveCandidateCommand,
)
from chappy.application.identify import CandidateLineSnapshot
from chappy.core.velocity_ranges import LineAnalysisHalfWidth


@dataclass(slots=True)
class _IdentifyPort:
    """Identify history port test double."""

    restored_candidates: list[tuple[CandidateLineSnapshot, ...]] = field(default_factory=list)
    removed_candidates: list[tuple[str, ...]] = field(default_factory=list)
    clear_count: int = 0
    updated_regions: list[tuple[str, ...]] = field(default_factory=list)

    def restore_identify_candidates(
        self, snapshots: tuple[CandidateLineSnapshot, ...]
    ) -> ChangeSet:
        """Record restored identify candidates."""
        self.restored_candidates.append(snapshots)
        return ChangeSet(changed_candidate_ids=tuple(snapshot.system_id for snapshot in snapshots))

    def remove_identify_candidates(self, system_ids: tuple[str, ...]) -> ChangeSet:
        """Record removed identify candidates."""
        self.removed_candidates.append(system_ids)
        return ChangeSet(changed_candidate_ids=system_ids)

    def clear_identify_candidates(self) -> ChangeSet:
        """Record candidate clearing."""
        self.clear_count += 1
        return ChangeSet.empty()

    def update_identify_region_analysis_ranges(self, region_ids: tuple[str, ...]) -> ChangeSet:
        """Record region analysis-range updates."""
        self.updated_regions.append(region_ids)
        return ChangeSet(changed_region_ids=region_ids)


@dataclass(slots=True)
class _OrganizePort:
    """Organize history port test double for identify registration."""

    restored_regions: list[tuple[AbsorptionRegionSnapshot, ...]] = field(default_factory=list)
    restored_lines: list[tuple[AbsorptionLineSnapshot, ...]] = field(default_factory=list)
    removed_lines: list[tuple[str, ...]] = field(default_factory=list)
    partial_regions: list[tuple[AbsorptionRegionSnapshot, ...]] = field(default_factory=list)

    def restore_absorption_regions(
        self, snapshots: tuple[AbsorptionRegionSnapshot, ...]
    ) -> ChangeSet:
        """Record restored absorption regions."""
        self.restored_regions.append(snapshots)
        return ChangeSet(changed_region_ids=tuple(snapshot.region_id for snapshot in snapshots))

    def restore_absorption_lines(
        self, snapshots: tuple[AbsorptionLineSnapshot, ...], *, restore_multiplet_links: bool
    ) -> ChangeSet:
        """Record restored absorption lines."""
        assert restore_multiplet_links is True
        self.restored_lines.append(snapshots)
        return ChangeSet(changed_line_ids=tuple(snapshot.line_id for snapshot in snapshots))

    def remove_absorption_lines(
        self, line_ids: tuple[str, ...], *, delete_models: bool
    ) -> ChangeSet:
        """Record removed absorption lines."""
        assert delete_models is False
        self.removed_lines.append(line_ids)
        return ChangeSet(changed_line_ids=line_ids)

    def apply_absorption_region_states_partial_exact(
        self, snapshots: tuple[AbsorptionRegionSnapshot, ...]
    ) -> ChangeSet:
        """Record exact affected-region application."""
        self.partial_regions.append(snapshots)
        return ChangeSet(changed_region_ids=tuple(item.region_id for item in snapshots))


def _candidate_snapshot(system_id: str) -> CandidateLineSnapshot:
    """Create one candidate snapshot."""
    return CandidateLineSnapshot(
        system_id=system_id,
        species="C IV",
        lambda_min=1547.0,
        lambda_max=1549.0,
        creation_method="manual",
        line_id=f"atomic-{system_id}",
        rest_wavelength=1548.2,
        center_z=2.0,
        multiplet_id="civ",
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
        analysis_half_width=LineAnalysisHalfWidth(200.0),
        tie_group_key="",
    )


def _line_snapshot(line_id: str, region_id: str) -> AbsorptionLineSnapshot:
    """Create one absorption line snapshot."""
    return AbsorptionLineSnapshot(
        line_id=line_id,
        species="C IV",
        rest_wavelength=1548.2,
        center_z=2.0,
        window_kms=200.0,
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.19,
        gamma_value=2.64e8,
        lambda_range=(1547.0, 1549.0),
        region_id=region_id,
        multiplet_ids=(),
        model_ids=(),
        needs_optimization=True,
        created_by="identify",
        created_at=datetime.now(UTC),
    )


def _region_snapshot(region_id: str) -> AbsorptionRegionSnapshot:
    """Create one absorption region snapshot."""
    return AbsorptionRegionSnapshot(
        region_id=region_id,
        line_ids=("line-1",),
        display_color="#123456",
        analysis_range=(1547.0, 1549.0),
        created_at=datetime.now(UTC),
    )


def test_identify_add_candidate_command_restores_and_removes_candidates() -> None:
    """Verify candidate add history uses typed identify port calls."""
    snapshot = _candidate_snapshot("candidate-1")
    port = _IdentifyPort()
    command = IdentifyAddCandidateCommand(snapshots=(snapshot,))
    context = HistoryCommandContext(identify_port=port)

    redo = command.redo(context)
    undo = command.undo(context)

    assert redo.success is True
    assert undo.success is True
    assert port.restored_candidates == [(snapshot,)]
    assert port.removed_candidates == [("candidate-1",)]


def test_identify_remove_candidate_command_removes_and_restores_candidates() -> None:
    """Verify candidate remove history uses typed identify port calls."""
    snapshot = _candidate_snapshot("candidate-1")
    port = _IdentifyPort()
    command = IdentifyRemoveCandidateCommand(system_ids=("candidate-1",), snapshots=(snapshot,))
    context = HistoryCommandContext(identify_port=port)

    redo = command.redo(context)
    undo = command.undo(context)

    assert redo.success is True
    assert undo.success is True
    assert port.removed_candidates == [("candidate-1",)]
    assert port.restored_candidates == [(snapshot,)]


def test_identify_clear_candidates_command_clears_and_restores_candidates() -> None:
    """Verify candidate clear history restores captured typed snapshots."""
    snapshot = _candidate_snapshot("candidate-1")
    port = _IdentifyPort()
    command = IdentifyClearCandidatesCommand(snapshots=(snapshot,))
    context = HistoryCommandContext(identify_port=port)

    redo = command.redo(context)
    undo = command.undo(context)

    assert redo.success is True
    assert undo.success is True
    assert port.clear_count == 1
    assert port.restored_candidates == [(snapshot,)]


def test_identify_register_selected_command_replays_and_reverts_registration() -> None:
    """Verify selected registration history coordinates identify and organize ports."""
    candidate = _candidate_snapshot("candidate-1")
    line = _line_snapshot("line-1", "region-1")
    region = _region_snapshot("region-1")
    identify_port = _IdentifyPort()
    organize_port = _OrganizePort()
    command = IdentifyRegisterSelectedCommand(
        created_line_ids=("line-1",),
        removed_system_ids=("candidate-1",),
        candidate_snapshots=(candidate,),
        affected_region_ids=("region-1",),
        line_snapshots=(line,),
        before_affected_region_snapshots=(),
        after_affected_region_snapshots=(region,),
    )
    context = HistoryCommandContext(identify_port=identify_port, organize_port=organize_port)

    redo = command.redo(context)
    undo = command.undo(context)

    assert redo.success is True
    assert undo.success is True
    assert identify_port.removed_candidates == [("candidate-1",)]
    assert identify_port.restored_candidates == [(candidate,)]
    assert identify_port.updated_regions == []
    assert organize_port.restored_regions == [(region,)]
    assert organize_port.restored_lines == [(line,)]
    assert organize_port.removed_lines == [("line-1",)]
    assert organize_port.partial_regions == [(region,), ()]
