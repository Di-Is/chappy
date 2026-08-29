"""Use cases for mutating project-owned analysis artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts.ports import AnalysisArtifactStorePort
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion


class SuccessfulAnalysisProjectPort(AnalysisArtifactStorePort, Protocol):
    """Project operations required to commit successful analysis atomically."""

    modified: datetime
    absorption_lines: dict[str, AbsorptionLine]
    absorption_regions: dict[str, AbsorptionRegion]

    def clear_region_needs_optimization(self, region_id: str) -> int:
        """Clear the reanalysis flags for one region."""
        ...


@dataclass(frozen=True, slots=True)
class _SuccessfulAnalysisSnapshot:
    """Project state restored if a successful-fit commit fails."""

    modified: datetime
    analysis_state: RegionAnalysisState
    optimization_flags: tuple[tuple[str, bool], ...]


class AnalysisArtifactStoreUseCase:
    """Apply explicit region analysis state transitions."""

    def record_artifact(
        self, store: AnalysisArtifactStorePort, region_id: str, summary: FitSummary
    ) -> AnalysisArtifact:
        """Store fit evidence against the region's current input revision."""
        state = self._require_state(store, region_id)
        artifact = AnalysisArtifact(
            region_id=region_id, source_revision=state.current_revision, fit_summary=summary
        )
        store.set_region_analysis_state(
            RegionAnalysisState(
                region_id=region_id, current_revision=state.current_revision, artifact=artifact
            )
        )
        return artifact

    def invalidate(self, store: AnalysisArtifactStorePort, region_id: str) -> None:
        """Advance a region revision while retaining its prior evidence as stale."""
        self.invalidate_regions(store, (region_id,))

    def invalidate_regions(
        self, store: AnalysisArtifactStorePort, region_ids: Iterable[str]
    ) -> tuple[str, ...]:
        """Atomically advance revisions for multiple regions."""
        requested = tuple(dict.fromkeys(region_ids))
        states = tuple(self._require_state(store, region_id) for region_id in requested)
        store.set_region_analysis_states(
            RegionAnalysisState(
                region_id=state.region_id,
                current_revision=AnalysisRevision(state.current_revision.value + 1),
                artifact=state.artifact,
            )
            for state in states
        )
        return requested

    def invalidate_all_analysis_capable(self, store: AnalysisArtifactStorePort) -> tuple[str, ...]:
        """Atomically advance every region that currently supports analysis."""
        return self.invalidate_regions(
            store,
            (
                state.region_id
                for state in store.region_analysis_states()
                if store.is_region_analysis_capable(state.region_id)
            ),
        )

    def restore(self, store: AnalysisArtifactStorePort, state: RegionAnalysisState) -> None:
        """Restore an exact region state captured before a transaction."""
        store.set_region_analysis_state(state)

    @staticmethod
    def _require_state(store: AnalysisArtifactStorePort, region_id: str) -> RegionAnalysisState:
        state = store.region_analysis_state(region_id)
        if state is None:
            msg = f"Analysis region not found: {region_id}"
            raise ValueError(msg)
        return state


class RecordSuccessfulAnalysisUseCase:
    """Commit fit evidence and line freshness as one project transaction."""

    def __init__(self, *, artifacts: AnalysisArtifactStoreUseCase | None = None) -> None:
        """Initialize with the canonical artifact transition service."""
        self._artifacts = artifacts or AnalysisArtifactStoreUseCase()

    def execute(
        self, project: SuccessfulAnalysisProjectPort, region_id: str, summary: FitSummary
    ) -> AnalysisArtifact:
        """Record one successful fit, rolling back every touched fact on failure."""
        state = project.region_analysis_state(region_id)
        region = project.absorption_regions.get(region_id)
        if state is None or region is None:
            msg = f"Analysis region not found: {region_id}"
            raise ValueError(msg)
        missing_line_ids = [
            line_id for line_id in region.line_ids if line_id not in project.absorption_lines
        ]
        if missing_line_ids:
            msg = f"Analysis region contains missing lines: {', '.join(missing_line_ids)}"
            raise ValueError(msg)

        snapshot = _SuccessfulAnalysisSnapshot(
            modified=project.modified,
            analysis_state=state,
            optimization_flags=tuple(
                (line_id, project.absorption_lines[line_id].needs_optimization)
                for line_id in region.line_ids
            ),
        )
        try:
            artifact = self._artifacts.record_artifact(project, region_id, summary)
            project.clear_region_needs_optimization(region_id)
        except Exception:
            self._artifacts.restore(project, snapshot.analysis_state)
            for line_id, needs_optimization in snapshot.optimization_flags:
                project.absorption_lines[line_id].needs_optimization = needs_optimization
            project.modified = snapshot.modified
            raise
        return artifact
