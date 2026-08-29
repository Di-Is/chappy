"""Side-effect-free impact preview for Identify candidate registration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.core.velocity_ranges import LineAnalysisHalfWidth

from .models import (
    BuildRegionPreviewsRequest,
    CandidateLineSnapshot,
    ExistingRegionSnapshot,
    IdentifyRegistrationPlan,
)
from .registration_usecase import BuildIdentifyRegistrationPlanUseCase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
    from chappy.core.identify_state import CandidateLine
    from chappy.core.velocity_ranges import MultipletGroupingVelocityTolerance


class IdentifyRegistrationImpactProjectPort(Protocol):
    """Read-only project state required for exact registration impact preview."""

    def list_absorption_regions(self) -> list[AbsorptionRegion]:
        """Return current regions in storage order."""
        ...

    def list_absorption_lines(self) -> list[AbsorptionLine]:
        """Return current absorption lines in storage order."""
        ...


class IdentifyRegistrationImpactSessionPort(Protocol):
    """Read-only Identify session state required for exact impact preview."""

    @property
    def candidate_lines(self) -> Sequence[CandidateLine]:
        """Return current candidates in storage order."""
        ...


@dataclass(frozen=True, slots=True)
class IdentifyRegistrationImpactRequest:
    """Exact sources and targets for one side-effect-free registration preview."""

    project: IdentifyRegistrationImpactProjectPort
    session: IdentifyRegistrationImpactSessionPort
    candidates: tuple[CandidateLineSnapshot, ...]
    existing_regions: tuple[ExistingRegionSnapshot, ...]
    region_line_memberships: tuple[tuple[str, tuple[str, ...]], ...]
    multiplet_grouping_tolerance: MultipletGroupingVelocityTolerance
    unknown_label: str


class IdentifyRegistrationImpactPreviewUseCase:
    """Validate live sources and return their immutable normalized registration plan."""

    def __init__(self, planner: BuildIdentifyRegistrationPlanUseCase | None = None) -> None:
        """Initialize the preview with its pure planner."""
        self._planner = planner or BuildIdentifyRegistrationPlanUseCase()

    def preview(self, request: IdentifyRegistrationImpactRequest) -> IdentifyRegistrationPlan:
        """Return an exact plan without changing project, session, history, or revisions."""
        self._require_exact_sources(request)
        self._require_exact_region_targets(request)
        return self._planner.build(
            BuildRegionPreviewsRequest(
                candidates=request.candidates,
                existing_regions=request.existing_regions,
                multiplet_grouping_tolerance=request.multiplet_grouping_tolerance,
                unknown_label=request.unknown_label,
            )
        )

    @staticmethod
    def _require_exact_sources(request: IdentifyRegistrationImpactRequest) -> None:
        """Require unique requested candidates to equal current session objects."""
        requested_ids = tuple(candidate.system_id for candidate in request.candidates)
        if len(set(requested_ids)) != len(requested_ids):
            msg = "Identify registration candidate identities must be unique."
            raise ValueError(msg)

        session_candidates = {
            candidate.system_id: _candidate_snapshot(candidate)
            for candidate in request.session.candidate_lines
        }
        for candidate in request.candidates:
            current = session_candidates.get(candidate.system_id)
            if current is None:
                msg = (
                    f"Identify registration candidate is no longer present: {candidate.system_id}"
                )
                raise ValueError(msg)
            if current != candidate:
                msg = f"Identify registration candidate source is stale: {candidate.system_id}"
                raise ValueError(msg)

    @staticmethod
    def _require_exact_region_targets(request: IdentifyRegistrationImpactRequest) -> None:
        """Require preview region membership and ranges to match current project storage."""
        snapshots = request.existing_regions
        snapshot_ids = tuple(snapshot.region_id for snapshot in snapshots)
        if len(set(snapshot_ids)) != len(snapshot_ids):
            msg = "Identify registration region snapshot identities must be unique."
            raise ValueError(msg)

        current_regions = request.project.list_absorption_regions()
        current_ids = tuple(region.region_id for region in current_regions)
        if snapshot_ids != current_ids:
            msg = "Identify registration region targets are stale."
            raise ValueError(msg)
        current_memberships = tuple(
            (region.region_id, tuple(region.line_ids)) for region in current_regions
        )
        if request.region_line_memberships != current_memberships:
            msg = "Identify registration region membership targets are stale."
            raise ValueError(msg)

        current_lines = request.project.list_absorption_lines()
        expected_ranges = {
            region.region_id: tuple(
                line.lambda_range
                for line in current_lines
                if line.region_id == region.region_id and line.lambda_range is not None
            )
            for region in current_regions
        }
        for snapshot in snapshots:
            if snapshot.line_ranges != expected_ranges[snapshot.region_id]:
                msg = f"Identify registration region target is stale: {snapshot.region_id}"
                raise ValueError(msg)


def _candidate_snapshot(candidate: CandidateLine) -> CandidateLineSnapshot:
    """Convert one live session candidate into its exact scientific DTO."""
    return CandidateLineSnapshot(
        system_id=candidate.system_id,
        species=candidate.species,
        lambda_min=candidate.lambda_min,
        lambda_max=candidate.lambda_max,
        creation_method=candidate.creation_method,
        line_id=candidate.line_id,
        rest_wavelength=candidate.rest_wavelength,
        center_z=candidate.center_z,
        multiplet_id=candidate.multiplet_id,
        multiplet_label=candidate.multiplet_label,
        transition_name=candidate.transition_name,
        oscillator_strength=candidate.oscillator_strength,
        gamma_value=candidate.gamma_value,
        analysis_half_width=LineAnalysisHalfWidth(candidate.analysis_half_width_kms),
        tie_group_key=candidate.tie_group_key,
    )


__all__ = [
    "IdentifyRegistrationImpactPreviewUseCase",
    "IdentifyRegistrationImpactProjectPort",
    "IdentifyRegistrationImpactRequest",
    "IdentifyRegistrationImpactSessionPort",
]
