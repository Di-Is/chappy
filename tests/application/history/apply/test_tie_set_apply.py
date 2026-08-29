"""Integration tests for tie set edit undo/redo through HistoryApplyUseCase."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from chappy.application.history import HistoryRecorder
from chappy.application.history.apply.usecase import HistoryApplyUseCase
from chappy.application.history.snapshot_mapping import tie_set_snapshot
from chappy.application.optimize import (
    OptimizeParameterMutationUseCase,
    TieSetCreated,
    TieSetEditUseCase,
    TieSetRemovalRejected,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import (
    AnalysisArtifact,
    AnalysisRevision,
    FitSummary,
    RegionAnalysisState,
)
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.history import CommandHistory
from chappy.core.spectroscopy_project import SpectroscopyProject

from history_apply_fakes import build_usecase


def _history_with_project() -> tuple[
    CommandHistory, HistoryApplyUseCase, SpectroscopyProject, HistoryRecorder
]:
    """Build a command history connected to a fresh project via a real use case."""
    history = CommandHistory()
    project = SpectroscopyProject()
    line = AbsorptionLine(
        line_id="analysis-line",
        species="C IV",
        rest_wavelength=1548.2,
        center_z=1.2,
        window_kms=100.0,
        multiplet_label="C IV",
        transition_name="1548",
        oscillator_strength=0.1,
        gamma_value=1e8,
        region_id="analysis-region",
        needs_optimization=False,
    )
    project.load_absorption_state(
        regions={
            "analysis-region": AbsorptionRegion(
                region_id="analysis-region", line_ids=[line.line_id]
            )
        },
        lines={line.line_id: line},
    )
    revision = AnalysisRevision(1)
    project.set_region_analysis_state(
        RegionAnalysisState(
            region_id="analysis-region",
            current_revision=revision,
            artifact=AnalysisArtifact(
                region_id="analysis-region",
                source_revision=revision,
                fit_summary=FitSummary(chi_squared=1.0),
            ),
        )
    )
    project.modified = datetime(2020, 1, 1, tzinfo=UTC)
    usecase = build_usecase(project_provider=lambda: project)
    history.set_applier(usecase)
    recorder = HistoryRecorder(history, lambda: project)
    return history, usecase, project, recorder


def _assert_global_freshness(
    project: SpectroscopyProject, *, revision: int, artifact: AnalysisArtifact
) -> None:
    """Assert the shared global history freshness contract."""
    state = project.region_analysis_state("analysis-region")
    assert state is not None and state.current_revision == AnalysisRevision(revision)
    assert state.artifact is artifact
    assert state.artifact.source_revision == AnalysisRevision(1)
    assert project.absorption_lines["analysis-line"].needs_optimization
    assert project.modified > datetime(2020, 1, 1, tzinfo=UTC)


def _add_component(project: SpectroscopyProject, name: str) -> AbsorberComponent:
    """Add one absorber component to the project model."""
    component = AbsorberComponent(name=name, redshift=1.2)
    project.model.add_component(component)
    return component


def _usecase() -> TieSetEditUseCase:
    """Build the tie set edit use case for history tests."""
    return TieSetEditUseCase(
        redshift_tolerance=5e-5, parameter_mutation=OptimizeParameterMutationUseCase()
    )


def test_undo_of_create_unbinds_components_and_redo_rebinds() -> None:
    """Undoing a recorded creation dissolves the tie set; redo rebuilds it."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    first = _add_component(project, "a")
    second = _add_component(project, "b")

    result = _usecase().create_tie_set(
        project.model, (first, second), frozenset({"redshift", "b_parameter"})
    )
    assert isinstance(result, TieSetCreated)
    recorder.record_tie_set_create(
        result.tie_set.uid, result.before_component_states, tie_set_snapshot(result.tie_set), 0
    )
    artifact = project.region_analysis_state("analysis-region").artifact  # type: ignore[union-attr]
    assert artifact is not None

    assert history.undo().success
    assert first.tie_set is None
    assert second.tie_set is None
    assert tuple(project.model.iter_tie_sets()) == ()
    assert first.parameters["redshift"] is not second.parameters["redshift"]
    _assert_global_freshness(project, revision=2, artifact=artifact)

    assert history.redo().success
    restored = tuple(project.model.iter_tie_sets())
    assert len(restored) == 1
    assert restored[0].origin == "user"
    assert first.tie_set is restored[0]
    assert first.parameters["redshift"] is second.parameters["redshift"]
    _assert_global_freshness(project, revision=3, artifact=artifact)


def test_undo_of_remove_restores_multiplet_origin_and_shared_binding() -> None:
    """Undoing a removal restores multiplet origin and shared parameter edits."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    components = tuple(_add_component(project, name) for name in ("a", "b", "c"))
    tie_set = ParameterTieSet("multiplet-1")
    for component in components:
        tie_set.add_component(component)
    project.model.add_tie_set(tie_set)

    result = _usecase().remove_from_tie_set(project.model, (components[0],))
    assert not isinstance(result, TieSetRemovalRejected)
    applied = result[0]
    assert applied.after_snapshot is not None
    recorder.record_tie_set_remove(
        (applied.uid,),
        (applied.before_snapshot,),
        (0,),
        (applied.after_snapshot,),
        (0,),
        applied.after_component_states,
    )
    artifact = project.region_analysis_state("analysis-region").artifact  # type: ignore[union-attr]
    assert artifact is not None

    assert history.undo().success
    restored = tuple(project.model.iter_tie_sets())
    assert len(restored) == 1
    assert restored[0].origin == "multiplet"
    assert components[0].tie_set is restored[0]
    assert components[0].parameters["redshift"] is components[1].parameters["redshift"]
    restored[0].set_shared_parameter("redshift", 2.0)
    assert components[0].get_parameter_value("redshift") == 2.0
    assert components[2].get_parameter_value("redshift") == 2.0
    redshift_before = next(
        state.value
        for state in applied.before_snapshot.shared_parameters
        if state.name == "redshift"
    )
    restored[0].set_shared_parameter("redshift", redshift_before)
    _assert_global_freshness(project, revision=2, artifact=artifact)

    assert history.redo().success
    survivor = tuple(project.model.iter_tie_sets())
    assert len(survivor) == 1
    assert survivor[0].origin == "user"
    assert components[0].tie_set is None
    assert components[1].tie_set is survivor[0]
    _assert_global_freshness(project, revision=3, artifact=artifact)


def test_undo_of_dissolve_restores_full_tie_set() -> None:
    """Undoing a dissolution restores the tie set with both members."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    components = tuple(_add_component(project, name) for name in ("a", "b"))
    tie_set = ParameterTieSet("multiplet-1")
    for component in components:
        tie_set.add_component(component)
    project.model.add_tie_set(tie_set)

    result = _usecase().remove_from_tie_set(project.model, (components[0],))
    assert not isinstance(result, TieSetRemovalRejected)
    applied = result[0]
    assert applied.after_snapshot is None
    recorder.record_tie_set_remove(
        (applied.uid,), (applied.before_snapshot,), (0,), (), (), applied.after_component_states
    )
    assert tuple(project.model.iter_tie_sets()) == ()

    assert history.undo().success
    restored = tuple(project.model.iter_tie_sets())
    assert len(restored) == 1
    assert restored[0].origin == "multiplet"
    assert components[0].tie_set is restored[0]
    assert components[1].tie_set is restored[0]

    assert history.redo().success
    assert tuple(project.model.iter_tie_sets()) == ()
    assert components[0].tie_set is None
    assert components[1].tie_set is None


def test_undo_redo_of_external_share_creation_reattaches_inner_tie_set() -> None:
    """Redoing an external share creation reattaches the pre-existing inner tie set."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    inner_first = _add_component(project, "inner-first")
    inner_second = _add_component(project, "inner-second")
    direct = _add_component(project, "direct")
    inner = ParameterTieSet("inner")
    inner.add_component(inner_first)
    inner.add_component(inner_second)
    project.model.add_tie_set(inner)

    result = _usecase().create_tie_set(
        project.model, (direct, inner_first), frozenset({"redshift"})
    )
    assert isinstance(result, TieSetCreated)
    outer = result.tie_set
    recorder.record_tie_set_create(
        outer.uid, result.before_component_states, tie_set_snapshot(outer), 1
    )
    artifact = project.region_analysis_state("analysis-region").artifact  # type: ignore[union-attr]
    assert artifact is not None

    assert history.undo().success
    assert tuple(project.model.iter_tie_sets()) == (inner,)
    assert inner.parent_tie is None
    assert direct.tie_set is None
    _assert_global_freshness(project, revision=2, artifact=artifact)

    assert history.redo().success
    restored_by_id = {tie_set.tie_id: tie_set for tie_set in project.model.iter_tie_sets()}
    restored_outer = restored_by_id[outer.tie_id]
    assert inner.parent_tie is restored_outer
    assert restored_outer.member_uids == {inner.uid}
    assert direct.tie_set is restored_outer
    assert direct.parameters["redshift"] is restored_outer.shared_parameters["redshift"]
    assert inner_first.parameters["redshift"] is restored_outer.shared_parameters["redshift"]
    _assert_global_freshness(project, revision=3, artifact=artifact)


def test_undo_of_external_parent_dissolve_reattaches_surviving_inner_tie_set() -> None:
    """Undoing a parent dissolve reattaches the inner tie set that survived on the model."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    inner_first = _add_component(project, "inner-first")
    inner_second = _add_component(project, "inner-second")
    direct = _add_component(project, "direct")
    inner = ParameterTieSet("inner")
    inner.add_component(inner_first)
    inner.add_component(inner_second)
    project.model.add_tie_set(inner)
    usecase = _usecase()
    created = usecase.create_tie_set(project.model, (direct, inner_first), frozenset({"redshift"}))
    assert isinstance(created, TieSetCreated)
    outer_tie_id = created.tie_set.tie_id

    result = usecase.remove_from_tie_set(project.model, (direct,))
    assert not isinstance(result, TieSetRemovalRejected)
    applied = result[0]
    assert applied.after_snapshot is None
    recorder.record_tie_set_remove(
        (applied.uid,), (applied.before_snapshot,), (1,), (), (), applied.after_component_states
    )
    assert tuple(project.model.iter_tie_sets()) == (inner,)

    assert history.undo().success
    restored_by_id = {tie_set.tie_id: tie_set for tie_set in project.model.iter_tie_sets()}
    restored_outer = restored_by_id[outer_tie_id]
    assert inner.parent_tie is restored_outer
    assert direct.tie_set is restored_outer
    assert inner_first.parameters["redshift"] is restored_outer.shared_parameters["redshift"]

    assert history.redo().success
    assert tuple(project.model.iter_tie_sets()) == (inner,)
    assert inner.parent_tie is None
    assert direct.tie_set is None


def test_undo_of_partial_removal_from_nested_inner_preserves_external_share() -> None:
    """Undoing a partial removal from a surviving nested inner keeps the external share."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    inner_first = _add_component(project, "inner-first")
    inner_second = _add_component(project, "inner-second")
    inner_third = _add_component(project, "inner-third")
    direct = _add_component(project, "direct")
    inner = ParameterTieSet("inner")
    for component in (inner_first, inner_second, inner_third):
        inner.add_component(component)
    project.model.add_tie_set(inner)
    usecase = _usecase()
    created = usecase.create_tie_set(project.model, (direct, inner_first), frozenset({"redshift"}))
    assert isinstance(created, TieSetCreated)
    outer_tie_id = created.tie_set.tie_id

    result = usecase.remove_from_tie_set(project.model, (inner_first,))
    assert not isinstance(result, TieSetRemovalRejected)
    uids = tuple(applied.uid for applied in result)
    before_snapshots = tuple(applied.before_snapshot for applied in result)
    after_snapshots = tuple(
        applied.after_snapshot for applied in result if applied.after_snapshot is not None
    )
    after_states = tuple(state for applied in result for state in applied.after_component_states)
    before_indices_by_uid = {inner.uid: 0, created.tie_set.uid: 1}
    after_indices_by_uid = {
        tie_set.uid: index for index, tie_set in enumerate(project.model.iter_tie_sets())
    }
    recorder.record_tie_set_remove(
        uids,
        before_snapshots,
        tuple(before_indices_by_uid[snapshot.uid] for snapshot in before_snapshots),
        after_snapshots,
        tuple(after_indices_by_uid[snapshot.uid] for snapshot in after_snapshots),
        after_states,
    )
    assert inner.parent_tie is not None

    assert history.undo().success
    restored_by_id = {tie_set.tie_id: tie_set for tie_set in project.model.iter_tie_sets()}
    restored_inner = restored_by_id["inner"]
    restored_outer = restored_by_id[outer_tie_id]
    assert restored_inner.parent_tie is restored_outer
    assert restored_outer.member_uids == {inner.uid}
    assert inner_first.tie_set is restored_inner
    assert inner_first.parameters["redshift"] is restored_outer.shared_parameters["redshift"]

    assert history.redo().success
    redone_by_id = {tie_set.tie_id: tie_set for tie_set in project.model.iter_tie_sets()}
    assert redone_by_id["inner"].parent_tie is redone_by_id[outer_tie_id]
    assert inner_first.tie_set is None


def test_restore_tie_sets_removes_only_the_matching_uid_when_tie_ids_collide() -> None:
    """A stale-uid clear must not dissolve a different tie set sharing the same tie_id."""
    _history, usecase, project, _recorder = _history_with_project()
    first_a = _add_component(project, "first-a")
    first_b = _add_component(project, "first-b")
    second_a = _add_component(project, "second-a")
    second_b = _add_component(project, "second-b")
    first = ParameterTieSet("multiplet-1")
    first.add_component(first_a)
    first.add_component(first_b)
    second = ParameterTieSet("multiplet-1")
    second.add_component(second_a)
    second.add_component(second_b)
    project.model.add_tie_set(first)
    project.model.add_tie_set(second)

    usecase._model_applier.restore_tie_sets((), tie_set_indices=(), removed_uids=(first.uid,))

    remaining = tuple(project.model.iter_tie_sets())
    assert remaining == (second,)
    assert first_a.tie_set is None
    assert first_b.tie_set is None
    assert second_a.tie_set is second
    assert second_b.tie_set is second
    assert second_a.parameters["redshift"] is second_b.parameters["redshift"]


def test_tie_undo_redo_restores_exact_global_order_and_transfers_stack() -> None:
    """Public Undo/Redo restores a middle tie index without replacing unaffected ties."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    pairs = tuple(
        (_add_component(project, f"{name}-a"), _add_component(project, f"{name}-b"))
        for name in ("first", "target", "last")
    )
    first_tie = ParameterTieSet("first")
    target_tie = ParameterTieSet("target")
    last_tie = ParameterTieSet("last")
    for tie_set, components in zip((first_tie, target_tie, last_tie), pairs, strict=True):
        for component in components:
            tie_set.add_component(component)
        project.model.add_tie_set(tie_set)

    result = _usecase().remove_from_tie_set(project.model, (pairs[1][0],))
    assert not isinstance(result, TieSetRemovalRejected)
    applied = result[0]
    assert applied.after_snapshot is None
    assert tuple(project.model.iter_tie_sets()) == (first_tie, last_tie)
    recorder.record_tie_set_remove(
        (applied.uid,), (applied.before_snapshot,), (1,), (), (), applied.after_component_states
    )
    assert history.can_undo and not history.can_redo

    assert history.undo().success
    restored = tuple(project.model.iter_tie_sets())
    assert tuple(tie_set.uid for tie_set in restored) == (
        first_tie.uid,
        target_tie.uid,
        last_tie.uid,
    )
    assert restored[0] is first_tie and restored[2] is last_tie
    assert not history.can_undo and history.can_redo

    assert history.redo().success
    assert tuple(project.model.iter_tie_sets()) == (first_tie, last_tie)
    assert history.can_undo and not history.can_redo


def test_restore_nested_tie_sets_preserves_inner_direct_membership() -> None:
    """Restoring stale nested tie sets should detach before removing direct members."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    inner_first = _add_component(project, "inner-first")
    inner_second = _add_component(project, "inner-second")
    direct = _add_component(project, "direct")
    inner = ParameterTieSet("inner")
    inner.add_component(inner_first)
    inner.add_component(inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)
    project.model.add_tie_set(inner)
    project.model.add_tie_set(outer)

    before_snapshots = (tie_set_snapshot(inner), tie_set_snapshot(outer))
    recorder.record_tie_set_remove((inner.uid, outer.uid), before_snapshots, (0, 1), (), (), ())

    assert history.undo().success
    restored_by_id = {tie_set.tie_id: tie_set for tie_set in project.model.iter_tie_sets()}
    restored_inner = restored_by_id["inner"]
    restored_outer = restored_by_id["outer"]
    assert restored_inner.parent_tie is restored_outer
    assert restored_outer.member_uids == {inner.uid}
    assert inner_first.tie_set is restored_inner
    assert inner_second.tie_set is restored_inner
    assert direct.tie_set is restored_outer
    assert inner_first.parameters["redshift"] is restored_outer.shared_parameters["redshift"]

    assert history.redo().success
    assert tuple(project.model.iter_tie_sets()) == ()
    assert inner_first.tie_set is None
    assert inner_second.tie_set is None
    assert direct.tie_set is None


def test_tie_rebuild_failure_restores_exact_identity_freshness_and_stack() -> None:
    """A failed tie Undo restores the original tie object and shared parameter identity."""
    history, _usecase_under_test, project, recorder = _history_with_project()
    first = _add_component(project, "a")
    second = _add_component(project, "b")
    result = _usecase().create_tie_set(project.model, (first, second), frozenset({"redshift"}))
    assert isinstance(result, TieSetCreated)
    tie_set = result.tie_set
    shared = first.parameters["redshift"]
    recorder.record_tie_set_create(
        tie_set.uid, result.before_component_states, tie_set_snapshot(tie_set), 0
    )
    states_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified
    history_before = history.get_state()

    with (
        patch.object(
            project.model, "rebuild_model_storage", side_effect=RuntimeError("tie rebuild failed")
        ),
        pytest.raises(RuntimeError, match="tie rebuild failed"),
    ):
        history.undo()

    assert tuple(project.model.iter_tie_sets()) == (tie_set,)
    assert first.tie_set is tie_set and second.tie_set is tie_set
    assert first.parameters["redshift"] is shared
    assert second.parameters["redshift"] is shared
    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert not project.absorption_lines["analysis-line"].needs_optimization
    assert project.modified == modified_before
    assert history.get_state() == history_before


def test_tie_exact_target_no_change_is_fully_inert() -> None:
    """An already-restored tie target changes only the Undo/Redo stack."""
    history, usecase, project, recorder = _history_with_project()
    first = _add_component(project, "a")
    second = _add_component(project, "b")
    result = _usecase().create_tie_set(project.model, (first, second), frozenset({"redshift"}))
    assert isinstance(result, TieSetCreated)
    recorder.record_tie_set_create(
        result.tie_set.uid, result.before_component_states, tie_set_snapshot(result.tie_set), 0
    )
    usecase._model_applier.restore_tie_sets(
        (), tie_set_indices=(), removed_uids=(result.tie_set.uid,)
    )
    usecase._model_applier.restore_component_parameters(result.before_component_states)
    states_before = project.stored_region_analysis_states_for_transaction()
    modified_before = project.modified

    assert history.undo().success

    assert project.stored_region_analysis_states_for_transaction() == states_before
    assert project.modified == modified_before
    assert not project.absorption_lines["analysis-line"].needs_optimization
