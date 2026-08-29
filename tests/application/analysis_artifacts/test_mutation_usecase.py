"""Tests for atomic scientific mutation invalidation."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime

import numpy as np
import pytest

from chappy.application.analysis_artifacts import (
    AnalysisArtifactStoreUseCase,
    AnalysisMutationImpact,
    AnalysisMutationOutcome,
    GlobalAnalysisMutationUseCase,
    RegionLocalAtomicMutationUseCase,
    RegionLocalMutationRequest,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision, FitSummary, RegionAnalysisState
from chappy.core.change_set import ChangeSet
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.events import ModelUpdated
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum


def _add_region(project: SpectroscopyProject, region_id: str) -> None:
    """Add one analysis-capable region."""
    line_id = f"line-{region_id}"
    project.absorption_lines[line_id] = AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="Ly alpha",
        transition_name="Ly alpha",
        oscillator_strength=0.4,
        gamma_value=1e8,
        region_id=region_id,
        needs_optimization=False,
    )
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=[line_id]
    )


def _project_with_model() -> tuple[SpectroscopyProject, AbsorberComponent]:
    """Return a project with one valid calculated absorber component."""
    project = SpectroscopyProject()
    wavelength = np.linspace(1200.0, 1230.0, 121)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength))
    )
    component = AbsorberComponent(
        component_id="absorber-1",
        wavelength=1215.67,
        column_density=13.0,
        b_parameter=15.0,
        redshift=0.0,
    )
    project.model.add_component(component)
    return project, component


@contextlib.contextmanager
def _atomic_history_scope():
    """Provide a rollback-capable no-op history scope for focused tests."""
    yield


def test_impact_deduplicates_region_identities_in_first_seen_order() -> None:
    """One command must increment a repeated affected identity only once."""
    impact = AnalysisMutationImpact.changed_regions(
        affected_region_ids=("region-2", "region-1", "region-2"),
        created_region_ids=("new", "new"),
        removed_region_ids=("old", "old"),
    )

    assert impact.affected_region_ids == ("region-2", "region-1")
    assert impact.created_region_ids == ("new",)
    assert impact.removed_region_ids == ("old",)


def test_no_change_impact_rejects_region_identities() -> None:
    """A no-change outcome cannot carry contradictory affected identities."""
    with pytest.raises(ValueError, match="no-change"):
        AnalysisMutationImpact(
            outcome=AnalysisMutationOutcome.NO_CHANGE, affected_region_ids=("region-1",)
        )


def test_no_change_skips_invalidation_and_history() -> None:
    """A rejected scientific edit must preserve every revision and history state."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    modified_before = project.modified
    history_calls: list[None] = []
    history_scope_events: list[str] = []

    @contextlib.contextmanager
    def history_scope():
        history_scope_events.append("enter")
        yield
        history_scope_events.append("exit")

    impact = GlobalAnalysisMutationUseCase().execute(
        project,
        mutate=lambda: False,
        rollback=lambda: None,
        record_history=lambda: history_calls.append(None),
        history_scope=history_scope,
    )

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert impact == AnalysisMutationImpact.no_change()
    assert state.current_revision == AnalysisRevision(0)
    assert project.modified == modified_before
    assert history_calls == []
    assert history_scope_events == ["enter", "exit"]


def test_history_failure_rolls_back_science_analysis_state_and_modified() -> None:
    """A history failure must not leave a partial global scientific command."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    AnalysisArtifactStoreUseCase().record_artifact(
        project, "region-1", FitSummary(chi_squared=1.0)
    )
    state_before = project.region_analysis_state("region-1")
    modified_before = project.modified
    flags_before = {
        line_id: line.needs_optimization for line_id, line in project.absorption_lines.items()
    }
    scientific_state = {"value": 0}
    scope_entries: list[str] = []

    @contextlib.contextmanager
    def _history_scope():
        scope_entries.append("enter")
        yield
        scope_entries.append("exit")

    def _mutate() -> bool:
        scientific_state["value"] = 1
        return True

    def _rollback() -> None:
        scientific_state["value"] = 0

    def _fail_history() -> None:
        raise RuntimeError("injected history failure")

    with pytest.raises(RuntimeError, match="injected history failure"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=_mutate,
            rollback=_rollback,
            record_history=_fail_history,
            history_scope=_history_scope,
        )

    assert scientific_state == {"value": 0}
    assert project.region_analysis_state("region-1") == state_before
    assert {
        line_id: line.needs_optimization for line_id, line in project.absorption_lines.items()
    } == flags_before
    assert project.modified == modified_before
    assert scope_entries == ["enter"]


def test_mutate_failure_rolls_back_partial_scientific_state() -> None:
    """A mutation callback failure should restore state changed before it raised."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    scientific_state = {"value": 0}

    def fail_mutation() -> bool:
        scientific_state["value"] = 1
        raise RuntimeError("injected mutate failure")

    with pytest.raises(RuntimeError, match="injected mutate failure"):
        GlobalAnalysisMutationUseCase().execute(
            project, mutate=fail_mutation, rollback=lambda: scientific_state.update(value=0)
        )

    assert scientific_state == {"value": 0}
    assert project.region_analysis_states()[0].current_revision == AnalysisRevision(0)


def test_mark_failure_rolls_back_revisions_flags_and_scientific_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial line-marking failure should restore every transaction fact."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    _add_region(project, "region-2")
    scientific_state = {"value": 0}
    original_mark = project.mark_region_needs_optimization

    def fail_second_mark(region_id: str) -> int:
        if region_id == "region-2":
            raise RuntimeError("injected mark failure")
        return original_mark(region_id)

    monkeypatch.setattr(project, "mark_region_needs_optimization", fail_second_mark)

    with pytest.raises(RuntimeError, match="injected mark failure"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: scientific_state.update(value=1) is None,
            rollback=lambda: scientific_state.update(value=0),
        )

    assert scientific_state == {"value": 0}
    assert all(
        state.current_revision == AnalysisRevision(0) for state in project.region_analysis_states()
    )
    assert all(not line.needs_optimization for line in project.absorption_lines.values())


@pytest.mark.parametrize("failure_phase", ["enter", "exit"])
def test_history_scope_failure_rolls_back_scientific_state(failure_phase: str) -> None:
    """Both history scope entry and exit failures belong to the rollback boundary."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    scientific_state = {"value": 0}

    @contextlib.contextmanager
    def failing_scope():
        if failure_phase == "enter":
            raise RuntimeError("injected scope enter failure")
        yield
        raise RuntimeError("injected scope exit failure")

    with pytest.raises(RuntimeError, match=f"injected scope {failure_phase} failure"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: scientific_state.update(value=1) is None,
            rollback=lambda: scientific_state.update(value=0),
            history_scope=failing_scope,
        )

    assert scientific_state == {"value": 0}
    assert project.region_analysis_states()[0].current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False


def test_rollback_failure_does_not_replace_original_failure() -> None:
    """Rollback diagnostics should be attached without hiding the triggering error."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")

    def fail_rollback() -> None:
        raise RuntimeError("injected rollback failure")

    def fail_history() -> None:
        raise ValueError("original history failure")

    with pytest.raises(ValueError, match="original history failure") as exc_info:
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: True,
            rollback=fail_rollback,
            record_history=fail_history,
            history_scope=_atomic_history_scope,
        )

    assert any("injected rollback failure" in note for note in exc_info.value.__notes__)
    assert project.region_analysis_states()[0].current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False


def test_restore_stages_continue_after_analysis_state_restore_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed revision restore should not prevent flags and modified restoration."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    modified_before = project.modified

    def fail_replace_states(states: object) -> None:
        _ = states
        raise RuntimeError("injected analysis restore failure")

    monkeypatch.setattr(
        project, "replace_region_analysis_states_for_transaction", fail_replace_states
    )

    def fail_history() -> None:
        raise ValueError("original history failure")

    with pytest.raises(ValueError, match="original history failure") as exc_info:
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: True,
            rollback=lambda: None,
            record_history=fail_history,
            history_scope=_atomic_history_scope,
        )

    assert any("analysis restore failure" in note for note in exc_info.value.__notes__)


def test_global_mutation_suppresses_storage_observers_until_history_commits() -> None:
    """Uncommitted parameter and derived states must be invisible to observers."""
    project, component = _project_with_model()
    model_events: list[ChangeSet] = []
    component_events: list[ChangeSet] = []
    project.model.events.subscribe(model_events.append)
    component.events.subscribe(component_events.append)
    history_calls: list[None] = []

    def record_history() -> None:
        assert model_events == []
        assert component_events == []
        assert project.model.is_model_valid is True
        history_calls.append(None)

    impact = GlobalAnalysisMutationUseCase().execute(
        project,
        mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
        rollback=lambda: component.set_parameter("column_density", 13.0),
        record_history=record_history,
        history_scope=_atomic_history_scope,
    )

    assert impact.changed is True
    assert history_calls == [None]
    assert component_events == []
    assert len(model_events) == 1
    assert model_events[0].contains(ModelUpdated)


def test_global_postcommit_listener_failure_keeps_science_and_runs_later_listener() -> None:
    """A model listener failure cannot reject science or skip later listeners."""
    project, component = _project_with_model()
    later_events: list[ChangeSet] = []

    def fail_listener(_changes: ChangeSet) -> None:
        raise RuntimeError("injected model listener failure")

    project.model.events.subscribe(fail_listener)
    project.model.events.subscribe(later_events.append)

    impact = GlobalAnalysisMutationUseCase().execute(
        project,
        mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
        rollback=lambda: component.set_parameter("column_density", 13.0),
    )

    assert impact.changed is True
    assert component.parameters["column_density"].value == 14.0
    assert len(later_events) == 1
    assert later_events[0].contains(ModelUpdated)


def test_global_postcommit_publisher_failure_does_not_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing post-commit publisher cannot reach caller science-failure handling."""
    project, component = _project_with_model()

    def fail_publisher(_changes: ChangeSet) -> None:
        raise RuntimeError("injected publisher failure")

    monkeypatch.setattr(project.model, "publish_storage_changes", fail_publisher)

    impact = GlobalAnalysisMutationUseCase().execute(
        project,
        mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
        rollback=lambda: component.set_parameter("column_density", 13.0),
    )

    assert impact.changed is True
    assert component.parameters["column_density"].value == 14.0


def test_global_postcommit_change_builder_failure_does_not_escape() -> None:
    """A failing post-commit change builder cannot misreport accepted science."""
    project, component = _project_with_model()

    def fail_change_builder() -> ChangeSet:
        raise RuntimeError("injected change builder failure")

    impact = GlobalAnalysisMutationUseCase().execute(
        project,
        mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
        rollback=lambda: component.set_parameter("column_density", 13.0),
        postcommit_changes=fail_change_builder,
    )

    assert impact.changed is True
    assert component.parameters["column_density"].value == 14.0


@pytest.mark.parametrize("starts_valid", [True, False])
def test_global_failure_restores_exact_derived_cache_without_events(starts_valid: bool) -> None:
    """Rollback restores valid and invalid runtime cache states byte-for-byte."""
    project, component = _project_with_model()
    if not starts_valid:
        project.model.invalidate_model()
    derived_before = project.model.snapshot_derived_state_for_transaction()
    modified_before = project.modified
    model_events: list[ChangeSet] = []
    component_events: list[ChangeSet] = []
    project.model.events.subscribe(model_events.append)
    component.events.subscribe(component_events.append)

    def fail_history() -> None:
        raise RuntimeError("injected cache rollback failure")

    with pytest.raises(RuntimeError, match="injected cache rollback failure"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
            rollback=lambda: component.set_parameter("column_density", 13.0),
            record_history=fail_history,
            history_scope=_atomic_history_scope,
        )

    derived_after = project.model.snapshot_derived_state_for_transaction()
    assert component.parameters["column_density"].value == 13.0
    assert derived_after.model_valid is derived_before.model_valid
    np.testing.assert_array_equal(derived_after.model_flux, derived_before.model_flux)
    np.testing.assert_array_equal(derived_after.residuals, derived_before.residuals)
    np.testing.assert_array_equal(derived_after.raw_model_flux, derived_before.raw_model_flux)
    assert project.modified == modified_before
    assert model_events == []
    assert component_events == []


def test_global_changed_without_regions_marks_science_and_publishes_once() -> None:
    """A changed regionless project still becomes dirty and publishes one event."""
    project = SpectroscopyProject()
    project.modified = datetime(2025, 1, 1, tzinfo=UTC)
    model_events: list[ChangeSet] = []
    project.model.events.subscribe(model_events.append)
    state = {"value": 0}

    impact = GlobalAnalysisMutationUseCase().execute(
        project,
        mutate=lambda: state.update(value=1) is None,
        rollback=lambda: state.update(value=0),
    )

    assert impact.changed is True
    assert impact.affected_region_ids == ()
    assert state == {"value": 1}
    assert project.modified > datetime(2025, 1, 1, tzinfo=UTC)
    assert len(model_events) == 1
    assert model_events[0].contains(ModelUpdated)


def test_region_local_request_deduplicates_and_invalidates_only_requested_regions() -> None:
    """One local command advances each repeated affected identity exactly once."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    _add_region(project, "region-2")
    history_calls: list[None] = []

    result = RegionLocalAtomicMutationUseCase().execute(
        project,
        RegionLocalMutationRequest(affected_region_ids=("region-2", "region-1", "region-2")),
        mutate=lambda: True,
        rollback=lambda: None,
        record_history=lambda: history_calls.append(None),
        history_scope=_atomic_history_scope,
    )

    assert result.impact.affected_region_ids == ("region-2", "region-1")
    assert [
        project.region_analysis_state(region_id).current_revision.value  # type: ignore[union-attr]
        for region_id in ("region-1", "region-2")
    ] == [1, 1]
    assert all(line.needs_optimization for line in project.absorption_lines.values())
    assert history_calls == [None]


def test_region_local_no_change_does_not_enter_history_or_touch_project() -> None:
    """A pure local NoChange preserves revisions, flags, modified, and history."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    modified_before = project.modified

    def unexpected_history_scope():
        raise AssertionError("NoChange must not enter history")

    result = RegionLocalAtomicMutationUseCase().execute(
        project,
        RegionLocalMutationRequest(affected_region_ids=("region-1",)),
        mutate=lambda: False,
        rollback=lambda: None,
        record_history=lambda: pytest.fail("NoChange must not record history"),
        history_scope=unexpected_history_scope,
    )

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert not result.changed
    assert state.current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert project.modified == modified_before


@pytest.mark.parametrize("region_id", ["missing", "incomplete"])
def test_region_local_rejects_invalid_region_before_mutation(region_id: str) -> None:
    """Missing and incomplete region identities fail before scientific mutation."""
    project = SpectroscopyProject()
    project.absorption_regions["incomplete"] = AbsorptionRegion(
        region_id="incomplete", line_ids=["missing-line"]
    )
    mutation_calls: list[None] = []

    with pytest.raises(ValueError, match="not found|not capable"):
        RegionLocalAtomicMutationUseCase().execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=(region_id,)),
            mutate=lambda: mutation_calls.append(None) is None,
            rollback=lambda: None,
        )

    assert mutation_calls == []


def test_region_local_history_failure_restores_artifact_flags_modified_and_science() -> None:
    """A local history failure restores every affected scientific fact exactly."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    AnalysisArtifactStoreUseCase().record_artifact(
        project, "region-1", FitSummary(chi_squared=2.0)
    )
    state_before = project.region_analysis_state("region-1")
    modified_before = project.modified
    scientific_state = {"value": 0}

    def fail_history() -> None:
        raise RuntimeError("local history failed")

    with pytest.raises(RuntimeError, match="local history failed"):
        RegionLocalAtomicMutationUseCase().execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=("region-1",)),
            mutate=lambda: scientific_state.update(value=1) is None,
            rollback=lambda: scientific_state.update(value=0),
            record_history=fail_history,
            history_scope=_atomic_history_scope,
        )

    assert scientific_state == {"value": 0}
    assert project.region_analysis_state("region-1") == state_before
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert project.modified == modified_before


def test_region_local_rollback_failure_preserves_original_exception() -> None:
    """Rollback diagnostics never replace the triggering local transaction error."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    modified_before = project.modified

    def fail_rollback() -> None:
        raise RuntimeError("local rollback failed")

    def fail_history() -> None:
        raise ValueError("original local failure")

    with pytest.raises(ValueError, match="original local failure") as exc_info:
        RegionLocalAtomicMutationUseCase().execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=("region-1",)),
            mutate=lambda: True,
            rollback=fail_rollback,
            record_history=fail_history,
            history_scope=_atomic_history_scope,
        )

    assert any("local rollback failed" in note for note in exc_info.value.__notes__)
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert project.modified == modified_before


def test_global_history_recording_requires_rollback_scope_before_mutation() -> None:
    """Global history configuration must fail before even a NoChange callback runs."""
    project = SpectroscopyProject()
    mutation_calls: list[None] = []

    with pytest.raises(ValueError, match="rollback scope"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: mutation_calls.append(None) is None,
            rollback=lambda: None,
            record_history=lambda: None,
        )

    assert mutation_calls == []


def test_region_local_history_recording_requires_rollback_scope_before_mutation() -> None:
    """Local history configuration must fail before validation or mutation."""
    project = SpectroscopyProject()
    mutation_calls: list[None] = []

    with pytest.raises(ValueError, match="rollback scope"):
        RegionLocalAtomicMutationUseCase().execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=("missing",)),
            mutate=lambda: mutation_calls.append(None) is None,
            rollback=lambda: None,
            record_history=lambda: None,
        )

    assert mutation_calls == []


def test_global_partial_history_push_restores_exact_mixed_analysis_storage() -> None:
    """A recorder failure restores history, science, and explicit state order exactly."""
    project = SpectroscopyProject()
    for region_id in ("region-1", "region-2", "region-3"):
        _add_region(project, region_id)
    explicit_second = RegionAnalysisState(
        region_id="region-2", current_revision=AnalysisRevision(4)
    )
    explicit_first = RegionAnalysisState(
        region_id="region-1", current_revision=AnalysisRevision(2)
    )
    project.replace_region_analysis_states_for_transaction((explicit_second, explicit_first))
    stored_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified
    scientific_state = {"value": 0}
    history_stack: list[str] = []

    @contextlib.contextmanager
    def history_scope():
        stack_before = list(history_stack)
        try:
            yield
        except Exception:
            history_stack[:] = stack_before
            raise

    def push_then_fail() -> None:
        history_stack.append("partial")
        raise RuntimeError("global recorder failed after push")

    with pytest.raises(RuntimeError, match="global recorder failed after push"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: scientific_state.update(value=1) is None,
            rollback=lambda: scientific_state.update(value=0),
            record_history=push_then_fail,
            history_scope=history_scope,
        )

    assert history_stack == []
    assert scientific_state == {"value": 0}
    assert project.stored_region_analysis_states_for_transaction() == stored_before
    assert project.region_analysis_state("region-3") == RegionAnalysisState(
        region_id="region-3", current_revision=AnalysisRevision()
    )
    assert all(not line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified == modified_before


def test_region_local_partial_history_push_restores_implicit_state_and_order() -> None:
    """A local recorder failure removes newly explicit state and restores its stack."""
    project = SpectroscopyProject()
    for region_id in ("region-1", "region-2", "region-3"):
        _add_region(project, region_id)
    explicit_second = RegionAnalysisState(
        region_id="region-2", current_revision=AnalysisRevision(5)
    )
    explicit_first = RegionAnalysisState(
        region_id="region-1", current_revision=AnalysisRevision(3)
    )
    project.replace_region_analysis_states_for_transaction((explicit_second, explicit_first))
    stored_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified
    scientific_state = {"value": 0}
    history_stack: list[str] = []

    @contextlib.contextmanager
    def history_scope():
        stack_before = list(history_stack)
        try:
            yield
        except Exception:
            history_stack[:] = stack_before
            raise

    def push_then_fail() -> None:
        history_stack.append("partial")
        raise RuntimeError("local recorder failed after push")

    with pytest.raises(RuntimeError, match="local recorder failed after push"):
        RegionLocalAtomicMutationUseCase().execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=("region-3",)),
            mutate=lambda: scientific_state.update(value=1) is None,
            rollback=lambda: scientific_state.update(value=0),
            record_history=push_then_fail,
            history_scope=history_scope,
        )

    assert history_stack == []
    assert scientific_state == {"value": 0}
    assert project.stored_region_analysis_states_for_transaction() == stored_before
    assert project.region_analysis_state("region-3") == RegionAnalysisState(
        region_id="region-3", current_revision=AnalysisRevision()
    )
    assert project.absorption_lines["line-region-3"].needs_optimization is False
    assert project.modified == modified_before


def test_region_local_history_scope_exit_failure_restores_exact_storage() -> None:
    """A local history-scope exit failure stays inside the scientific boundary."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")
    stored_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified
    scientific_state = {"value": 0}

    @contextlib.contextmanager
    def failing_scope():
        yield
        raise RuntimeError("local scope exit failed")

    with pytest.raises(RuntimeError, match="local scope exit failed"):
        RegionLocalAtomicMutationUseCase().execute(
            project,
            RegionLocalMutationRequest(affected_region_ids=("region-1",)),
            mutate=lambda: scientific_state.update(value=1) is None,
            rollback=lambda: scientific_state.update(value=0),
            history_scope=failing_scope,
        )

    assert scientific_state == {"value": 0}
    assert project.stored_region_analysis_states_for_transaction() == stored_before
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert project.modified == modified_before


def test_derived_rebuild_failure_restores_cache_and_exact_analysis_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Derived rebuild failure restores cache plus implicit/explicit storage exactly."""
    project, component = _project_with_model()
    for region_id in ("region-1", "region-2", "region-3"):
        _add_region(project, region_id)
    project.replace_region_analysis_states_for_transaction(
        (
            RegionAnalysisState("region-2", AnalysisRevision(6)),
            RegionAnalysisState("region-1", AnalysisRevision(1)),
        )
    )
    states_before = project.stored_region_analysis_states_for_transaction()
    derived_before = project.model.snapshot_derived_state_for_transaction()
    modified_before = project.modified
    original_rebuild = project.model.rebuild_model_storage

    def rebuild_then_fail() -> ChangeSet:
        original_rebuild()
        raise RuntimeError("derived rebuild failed")

    monkeypatch.setattr(project.model, "rebuild_model_storage", rebuild_then_fail)

    with pytest.raises(RuntimeError, match="derived rebuild failed"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
            rollback=lambda: component.set_parameter("column_density", 13.0),
        )

    derived_after = project.model.snapshot_derived_state_for_transaction()
    assert component.parameters["column_density"].value == 13.0
    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert project.region_analysis_state("region-3") == RegionAnalysisState(
        region_id="region-3", current_revision=AnalysisRevision()
    )
    np.testing.assert_array_equal(derived_after.model_flux, derived_before.model_flux)
    np.testing.assert_array_equal(derived_after.residuals, derived_before.residuals)
    np.testing.assert_array_equal(derived_after.raw_model_flux, derived_before.raw_model_flux)
    assert derived_after.model_valid is derived_before.model_valid
    assert project.modified == modified_before


def test_notification_scope_exit_failure_rolls_back_science_history_and_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Notification exit failure remains inside the complete atomic boundary."""
    project, component = _project_with_model()
    _add_region(project, "region-1")
    states_before = project.stored_region_analysis_states_for_transaction()
    derived_before = project.model.snapshot_derived_state_for_transaction()
    modified_before = project.modified
    history_stack: list[str] = []
    scope_calls = 0
    original_notification_scope = project.model.suppress_scientific_notifications

    @contextlib.contextmanager
    def history_scope():
        stack_before = list(history_stack)
        try:
            yield
        except Exception:
            history_stack[:] = stack_before
            raise

    @contextlib.contextmanager
    def fail_first_notification_exit():
        nonlocal scope_calls
        scope_calls += 1
        current_call = scope_calls
        with original_notification_scope():
            yield
        if current_call == 1:
            raise RuntimeError("notification scope exit failed")

    monkeypatch.setattr(
        project.model, "suppress_scientific_notifications", fail_first_notification_exit
    )

    with pytest.raises(RuntimeError, match="notification scope exit failed"):
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
            rollback=lambda: component.set_parameter("column_density", 13.0),
            record_history=lambda: history_stack.append("committed"),
            history_scope=history_scope,
        )

    derived_after = project.model.snapshot_derived_state_for_transaction()
    assert scope_calls == 2
    assert history_stack == []
    assert component.parameters["column_density"].value == 13.0
    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    np.testing.assert_array_equal(derived_after.model_flux, derived_before.model_flux)
    np.testing.assert_array_equal(derived_after.residuals, derived_before.residuals)
    np.testing.assert_array_equal(derived_after.raw_model_flux, derived_before.raw_model_flux)
    assert derived_after.model_valid is derived_before.model_valid
    assert project.modified == modified_before


def test_notification_scope_rollback_reentry_failure_is_attached_to_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rollback-scope re-entry failure is diagnostic and never replaces the trigger."""
    project, component = _project_with_model()
    scope_calls = 0
    original_notification_scope = project.model.suppress_scientific_notifications

    @contextlib.contextmanager
    def fail_exit_then_reentry():
        nonlocal scope_calls
        scope_calls += 1
        current_call = scope_calls
        if current_call == 2:
            raise RuntimeError("notification rollback reentry failed")
        with original_notification_scope():
            yield
        raise ValueError("original notification exit failure")

    monkeypatch.setattr(project.model, "suppress_scientific_notifications", fail_exit_then_reentry)

    with pytest.raises(ValueError, match="original notification exit failure") as exc_info:
        GlobalAnalysisMutationUseCase().execute(
            project,
            mutate=lambda: component.set_parameter("column_density", 14.0) is not None,
            rollback=lambda: component.set_parameter("column_density", 13.0),
        )

    assert scope_calls == 2
    assert any("notification rollback reentry failed" in note for note in exc_info.value.__notes__)


@pytest.mark.parametrize("local", [False, True])
def test_missing_line_during_non_structure_rollback_adds_failure_note(local: bool) -> None:
    """A vanished line is diagnosed instead of silently skipping flag restoration."""
    project = SpectroscopyProject()
    _add_region(project, "region-1")

    def remove_line_then_fail() -> bool:
        project.absorption_lines.pop("line-region-1")
        raise RuntimeError("original non-structure failure")

    with pytest.raises(RuntimeError, match="original non-structure failure") as exc_info:
        if local:
            RegionLocalAtomicMutationUseCase().execute(
                project,
                RegionLocalMutationRequest(affected_region_ids=("region-1",)),
                mutate=remove_line_then_fail,
                rollback=lambda: None,
            )
        else:
            GlobalAnalysisMutationUseCase().execute(
                project, mutate=remove_line_then_fail, rollback=lambda: None
            )

    assert any("lines disappeared: line-region-1" in note for note in exc_info.value.__notes__)
