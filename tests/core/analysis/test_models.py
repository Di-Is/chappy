"""Tests for pure project analysis value types."""

from __future__ import annotations

import pytest

from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisReadiness,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)


def test_analysis_revision_accepts_only_non_negative_integers() -> None:
    """A region revision must not accept booleans, floats, or negative values."""
    assert AnalysisRevision().value == 0
    assert AnalysisRevision(3).value == 3

    with pytest.raises(TypeError, match="integer"):
        AnalysisRevision(True)
    with pytest.raises(TypeError, match="integer"):
        AnalysisRevision(1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative"):
        AnalysisRevision(-1)


def test_region_state_requires_matching_artifact_region() -> None:
    """A region state cannot contain an artifact produced for another region."""
    artifact = AnalysisArtifact(
        region_id="region-2",
        source_revision=AnalysisRevision(0),
        fit_summary=FitSummary(chi_squared=1.0),
    )

    with pytest.raises(ValueError, match="belong"):
        RegionAnalysisState(
            region_id="region-1", current_revision=AnalysisRevision(0), artifact=artifact
        )


def test_region_state_keeps_current_revision_beside_artifact_revision() -> None:
    """A region snapshot keeps current and artifact source revisions distinct."""
    artifact = AnalysisArtifact(
        region_id="region-1", source_revision=AnalysisRevision(2), fit_summary=FitSummary()
    )
    region = RegionAnalysisState(
        region_id="region-1", current_revision=AnalysisRevision(3), artifact=artifact
    )
    assert region.current_revision == AnalysisRevision(3)
    assert region.artifact == artifact


def test_only_latest_readiness_is_exportable() -> None:
    """Exportability is a derived property exclusive to latest artifacts."""
    assert AnalysisReadiness.LATEST.exportable is True
    assert all(
        readiness.exportable is False
        for readiness in AnalysisReadiness
        if readiness is not AnalysisReadiness.LATEST
    )
