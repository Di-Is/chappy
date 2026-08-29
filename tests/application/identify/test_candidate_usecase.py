"""Tests for identify candidate use cases."""

from __future__ import annotations

import math

import pytest

from chappy.application.identify import (
    AtomicLineSnapshot,
    BuildVelocityPreviewUseCase,
    CandidateCreationEntry,
    CandidateLineSnapshot,
    CreateCandidateFromVelocityUseCase,
    VelocityCandidateRequest,
)
from chappy.core.identify_state import (
    CandidateLine,
    CandidateLineContext,
    IDENTIFY_TEMP_SYSTEM_LIMIT,
    IdentifySessionState,
)
from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.core.velocity_ranges import LineAnalysisHalfWidth, NewCandidateAnalysisHalfWidth


def _line(
    line_id: str,
    species: str,
    wavelength: float,
    *,
    multiplet_id: str = "",
    transition_name: str = "",
    tie_group_key: str | None = None,
) -> AtomicLineSnapshot:
    """Create an atomic line snapshot for tests.

    Args:
        line_id: Atomic line ID.
        species: Species label.
        wavelength: Rest wavelength.
        multiplet_id: Multiplet identifier.
        transition_name: Transition display name.

    Returns:
        Atomic line snapshot.
    """
    return AtomicLineSnapshot(
        line_id=line_id,
        species=species,
        wavelength_angstrom=wavelength,
        oscillator_strength=0.1,
        gamma_value=1e8,
        multiplet_id=multiplet_id,
        multiplet_label="",
        transition_name=transition_name,
        tie_group_key=multiplet_id if tie_group_key is None else tie_group_key,
    )


def _candidate_snapshot(candidate: CandidateLine) -> CandidateLineSnapshot:
    """Convert a core candidate line to an application snapshot.

    Args:
        candidate: Candidate line stored in test session state.

    Returns:
        Immutable candidate line snapshot.
    """
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
        tie_group_key=candidate.tie_group_key,
        transition_name=candidate.transition_name,
        oscillator_strength=candidate.oscillator_strength,
        gamma_value=candidate.gamma_value,
        analysis_half_width=LineAnalysisHalfWidth(candidate.analysis_half_width_kms),
    )


class _SessionMutationAdapter:
    """Test adapter that applies application creation entries to core session state."""

    def __init__(self, session: IdentifySessionState) -> None:
        """Create an adapter for a test identify session."""
        self._session = session

    @property
    def candidate_snapshots(self) -> tuple[CandidateLineSnapshot, ...]:
        """Return current candidate snapshots."""
        return tuple(_candidate_snapshot(candidate) for candidate in self._session.candidate_lines)

    def add_candidate_creation_entry(self, creation_entry: CandidateCreationEntry) -> str:
        """Add a candidate from an application creation entry.

        Args:
            creation_entry: Candidate creation entry from the use case.

        Returns:
            Created candidate system ID.
        """
        entry = creation_entry.preview_entry
        context = CandidateLineContext(
            line_id=entry.line_id,
            rest_wavelength=entry.rest_wavelength,
            multiplet_id=entry.multiplet_id,
            multiplet_label=entry.multiplet_label,
            tie_group_key=entry.tie_group_key,
            transition_name=entry.transition_name,
            oscillator_strength=entry.oscillator_strength,
            gamma_value=entry.gamma_value,
            center_z=creation_entry.redshift,
        )
        candidate = self._session.add_candidate_line(
            entry.species,
            entry.lambda_min,
            entry.lambda_max,
            creation_method="manual",
            context=context,
            analysis_half_width=creation_entry.analysis_half_width,
        )
        return candidate.system_id


def test_preview_calculates_redshift_and_window() -> None:
    """Preview builder should derive redshift and velocity window."""
    baseline = _line("base", "Mg II", 2803.0, transition_name="2803")

    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=2803.0,
            baseline_line=baseline,
            preset_lines=(baseline,),
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(200.0),
            include_all_preview_lines=False,
        )
    )

    assert math.isclose(preview.redshift, 0.0, rel_tol=0.0, abs_tol=1e-12)
    assert len(preview.entries) == 1
    entry = preview.entries[0]
    expected_delta = baseline.wavelength_angstrom * (200.0 / LIGHT_SPEED_KMS)
    assert math.isclose(entry.lambda_min, baseline.wavelength_angstrom - expected_delta)
    assert math.isclose(entry.lambda_max, baseline.wavelength_angstrom + expected_delta)
    assert entry.line_id == "base"


def test_preview_rejects_invalid_baseline_rest_wavelength() -> None:
    """Invalid atomic baseline data should not produce a zero-redshift preview."""
    baseline = _line("base", "Mg II", 0.0)

    with pytest.raises(ValueError, match="Baseline rest wavelength must be positive"):
        BuildVelocityPreviewUseCase().build(
            VelocityCandidateRequest(
                observed_wavelength=2803.0,
                baseline_line=baseline,
                preset_lines=(baseline,),
                new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(200.0),
                include_all_preview_lines=False,
            )
        )


def test_preview_includes_same_multiplet_without_include_all() -> None:
    """Preview should include baseline multiplet members without include-all mode."""
    baseline = _line("base", "Mg II", 2803.0, multiplet_id="MGII")
    companion = _line("comp", "Mg II", 2796.0, multiplet_id="MGII")
    unrelated = _line("other", "Fe II", 2600.0)

    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=2803.0,
            baseline_line=baseline,
            preset_lines=(baseline, companion, unrelated),
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(200.0),
            include_all_preview_lines=False,
        )
    )

    assert {entry.line_id for entry in preview.entries} == {"base", "comp"}


def test_preview_uses_declared_tie_key_instead_of_atomic_multiplet_id() -> None:
    """DB multiplet metadata alone must not expand a preview."""
    baseline = _line("base", "Mg II", 2803.0, multiplet_id="MGII", tie_group_key="group-a")
    unrelated = _line("comp", "Mg II", 2796.0, multiplet_id="MGII", tie_group_key="group-b")

    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=2803.0,
            baseline_line=baseline,
            preset_lines=(baseline, unrelated),
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(200.0),
            include_all_preview_lines=False,
        )
    )

    assert tuple(entry.line_id for entry in preview.entries) == ("base",)


def test_preview_expands_same_declared_key_without_atomic_multiplet_id() -> None:
    """An explicit key expands a preview even when DB metadata is empty."""
    baseline = _line("base", "H I", 1215.67, tie_group_key="lyman-group")
    companion = _line("comp", "H I", 1025.72, tie_group_key="lyman-group")

    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=1215.67,
            baseline_line=baseline,
            preset_lines=(baseline, companion),
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(200.0),
            include_all_preview_lines=False,
        )
    )

    assert {entry.line_id for entry in preview.entries} == {"base", "comp"}
    assert {entry.tie_group_key for entry in preview.entries} == {"lyman-group"}
    assert {entry.multiplet_label for entry in preview.entries} == {"H I"}


def test_preview_filters_data_bounds() -> None:
    """Preview should drop lines outside observed data bounds."""
    baseline = _line("base", "Mg II", 2803.0)
    outside = _line("outside", "Fe II", 1000.0)

    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=2803.0,
            baseline_line=baseline,
            preset_lines=(baseline, outside),
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(100.0),
            include_all_preview_lines=True,
            data_bounds=(2500.0, 2900.0),
        )
    )

    assert [entry.line_id for entry in preview.entries] == ["base"]


def test_create_candidate_skips_duplicate() -> None:
    """Candidate creation should report duplicates without mutating twice."""
    baseline = _line("base", "Mg II", 2803.0)
    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=2803.0,
            baseline_line=baseline,
            preset_lines=(baseline,),
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(200.0),
            include_all_preview_lines=False,
        )
    )
    session = IdentifySessionState()
    usecase = CreateCandidateFromVelocityUseCase()
    entries = tuple(
        CandidateCreationEntry(
            preview_entry=entry,
            redshift=preview.redshift,
            analysis_half_width=LineAnalysisHalfWidth(200.0),
        )
        for entry in preview.entries
    )

    adapter = _SessionMutationAdapter(session)
    first = usecase.create(adapter, entries)
    second = usecase.create(adapter, entries)

    assert len(first.created) == 1
    assert len(second.created) == 0
    assert second.duplicate_count == 1
    assert session.temporary_count == 1


def test_creation_entry_keeps_range_and_saved_half_width_atomic() -> None:
    """Candidate creation must not re-read a changed future-candidate session draft."""
    baseline = _line("base", "Mg II", 2803.0)
    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=2803.0,
            baseline_line=baseline,
            preset_lines=(baseline,),
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(140.0),
            include_all_preview_lines=False,
        )
    )
    session = IdentifySessionState()
    session.set_new_candidate_analysis_half_width(NewCandidateAnalysisHalfWidth(500.0))
    entry = CandidateCreationEntry(
        preview_entry=preview.entries[0],
        redshift=preview.redshift,
        analysis_half_width=LineAnalysisHalfWidth(140.0),
    )

    result = CreateCandidateFromVelocityUseCase().create(
        _SessionMutationAdapter(session), (entry,)
    )

    assert len(result.created) == 1
    candidate = session.candidate_lines[0]
    assert candidate.analysis_half_width_kms == 140.0
    expected_delta = baseline.wavelength_angstrom * 140.0 / LIGHT_SPEED_KMS
    assert candidate.lambda_min == pytest.approx(baseline.wavelength_angstrom - expected_delta)
    assert candidate.lambda_max == pytest.approx(baseline.wavelength_angstrom + expected_delta)


class _ErrorProneMutationAdapter:
    """Adapter used to verify non-limit ValueError propagation."""

    @property
    def candidate_snapshots(self) -> tuple[CandidateLineSnapshot, ...]:
        """Return no existing candidate snapshots."""
        return ()

    def add_candidate_creation_entry(self, creation_entry: CandidateCreationEntry) -> str:
        """Raise unexpected mutation error without recovery."""
        raise ValueError("unexpected mutation failure")


def _create_identify_candidate_request(count: int) -> tuple[CandidateCreationEntry, ...]:
    """Build `count` creation entries for stable deterministic use-case tests."""
    lines = tuple(
        _line(
            f"line-{index}",
            "Mg II",
            2803.0 + index * 0.01,
            multiplet_id="MG",
            transition_name=f"{index}",
        )
        for index in range(count)
    )
    baseline = lines[0]
    preview = BuildVelocityPreviewUseCase().build(
        VelocityCandidateRequest(
            observed_wavelength=baseline.wavelength_angstrom,
            baseline_line=baseline,
            preset_lines=lines,
            new_candidate_analysis_half_width=NewCandidateAnalysisHalfWidth(200.0),
            include_all_preview_lines=True,
        )
    )
    return tuple(
        CandidateCreationEntry(
            preview_entry=entry,
            redshift=preview.redshift,
            analysis_half_width=LineAnalysisHalfWidth(200.0),
        )
        for entry in preview.entries
    )


def test_create_candidate_limit_reached_remains_recovered() -> None:
    """Candidate limit reached from session remains user-recoverable with this use case."""
    usecase = CreateCandidateFromVelocityUseCase()
    session = IdentifySessionState()
    adapter = _SessionMutationAdapter(session)

    entries = _create_identify_candidate_request(IDENTIFY_TEMP_SYSTEM_LIMIT + 1)
    result = usecase.create(adapter, entries)

    assert result.limit_reached is True
    assert len(result.created) == IDENTIFY_TEMP_SYSTEM_LIMIT
    assert result.duplicate_count == 0
    assert session.temporary_count == IDENTIFY_TEMP_SYSTEM_LIMIT


def test_create_candidate_unexpected_value_error_propagates() -> None:
    """Unexpected ValueError from mutation port must propagate without masking."""
    usecase = CreateCandidateFromVelocityUseCase()
    entries = _create_identify_candidate_request(1)

    with pytest.raises(ValueError, match="unexpected mutation failure"):
        usecase.create(_ErrorProneMutationAdapter(), entries)
