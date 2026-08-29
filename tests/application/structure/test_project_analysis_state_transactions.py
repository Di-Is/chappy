"""Tests for project-owned transaction-only analysis state APIs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chappy.core.absorption.models import AbsorptionRegion
from chappy.core.analysis import AnalysisRevision, RegionAnalysisState
from chappy.core.spectroscopy_project import SpectroscopyProject


def _project() -> SpectroscopyProject:
    """Build a project with two region identities."""
    project = SpectroscopyProject()
    project.absorption_regions = {
        "first": AbsorptionRegion(region_id="first"),
        "second": AbsorptionRegion(region_id="second"),
    }
    return project


def test_exact_replace_preserves_order_and_modified_time() -> None:
    """Transaction restore should replace, not merge, explicit state."""
    project = _project()
    fixed_modified = datetime(2020, 1, 1, tzinfo=UTC)
    project.modified = fixed_modified
    second = RegionAnalysisState("second", AnalysisRevision(2))
    first = RegionAnalysisState("first", AnalysisRevision(1))

    project.replace_region_analysis_states_for_transaction((second, first))
    project.replace_region_analysis_states_for_transaction((first,))

    assert project.stored_region_analysis_states_for_transaction() == (first,)
    assert project.modified == fixed_modified


def test_prune_and_reset_are_silent_and_exact() -> None:
    """Deleted and created regions should be removable without changing modified time."""
    project = _project()
    first = RegionAnalysisState("first", AnalysisRevision(3))
    second = RegionAnalysisState("second", AnalysisRevision(4))
    project.replace_region_analysis_states_for_transaction((first, second))
    fixed_modified = datetime(2020, 1, 1, tzinfo=UTC)
    project.modified = fixed_modified

    del project.absorption_regions["second"]
    project.prune_region_analysis_states_for_transaction()
    project.reset_region_analysis_states_for_transaction(("first",))

    assert project.stored_region_analysis_states_for_transaction() == ()
    assert project.region_analysis_state("first") == RegionAnalysisState(
        "first", AnalysisRevision()
    )
    assert project.modified == fixed_modified


def test_exact_replace_and_reset_validate_region_identities() -> None:
    """Transaction APIs should reject missing and duplicate region identities."""
    project = _project()
    first = RegionAnalysisState("first", AnalysisRevision())
    with pytest.raises(ValueError, match="Duplicate"):
        project.replace_region_analysis_states_for_transaction((first, first))
    with pytest.raises(ValueError, match="missing region"):
        project.replace_region_analysis_states_for_transaction(
            (RegionAnalysisState("missing", AnalysisRevision()),)
        )
    with pytest.raises(ValueError, match="not found for reset"):
        project.reset_region_analysis_states_for_transaction(("missing",))
