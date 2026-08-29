"""Tests for atomic region-local mask mutations."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np
import pytest

from chappy.application.analysis_artifacts import AnalysisArtifactStoreUseCase
from chappy.application.history import MaskDefinitionSnapshot
from chappy.application.optimize import (
    CreateMaskRequest,
    MaskMutationKind,
    MaskMutationUseCase,
    RemoveMaskRequest,
    UpdateMaskRequest,
)
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import FitSummary
from chappy.core.events import MasksChanged
from chappy.core.masking import MaskDefinition
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum

if TYPE_CHECKING:
    from collections.abc import Iterator


class _History:
    """Failure-injectable atomic mask history recorder."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.scope_entries = 0
        self.records: list[
            tuple[
                MaskMutationKind,
                str,
                MaskDefinitionSnapshot | None,
                MaskDefinitionSnapshot | None,
                int | None,
                int | None,
                tuple[str, ...],
            ]
        ] = []

    @contextmanager
    def atomic_recording(self) -> Iterator[None]:
        before = list(self.records)
        self.scope_entries += 1
        try:
            yield
        except Exception:
            self.records = before
            raise

    def record_mask_mutation(
        self,
        *,
        kind: MaskMutationKind,
        mask_id: str,
        before: MaskDefinitionSnapshot | None,
        after: MaskDefinitionSnapshot | None,
        before_index: int | None,
        after_index: int | None,
        affected_region_ids: tuple[str, ...],
    ) -> None:
        self.records.append(
            (kind, mask_id, before, after, before_index, after_index, affected_region_ids)
        )
        if self.fail:
            raise RuntimeError("mask history failed")


def _add_region(project: SpectroscopyProject, region_id: str, *, line_count: int = 1) -> None:
    line_ids: list[str] = []
    for index in range(line_count):
        line_id = f"line-{region_id}-{index}"
        project.absorption_lines[line_id] = AbsorptionLine(
            line_id=line_id,
            species="C IV",
            rest_wavelength=1548.2 + index,
            center_z=2.0,
            window_kms=100.0,
            multiplet_label="C IV",
            transition_name=str(index),
            oscillator_strength=0.1,
            gamma_value=1e8,
            region_id=region_id,
            needs_optimization=False,
        )
        line_ids.append(line_id)
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=line_ids
    )


def _project() -> SpectroscopyProject:
    project = SpectroscopyProject()
    _add_region(project, "region-1", line_count=2)
    _add_region(project, "region-2")
    return project


def _mask(mask_id: str, group_id: str, start: float = 100.0) -> MaskDefinition:
    return MaskDefinition.from_range(
        start, start + 10.0, identifier=mask_id, label=f"Mask {mask_id}"
    ).with_group_id(group_id)


def _revision(project: SpectroscopyProject, region_id: str) -> int:
    state = project.region_analysis_state(region_id)
    assert state is not None
    return state.current_revision.value


def _make_model_valid(project: SpectroscopyProject) -> None:
    wavelength = np.linspace(90.0, 150.0, 40, dtype=np.float64)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength), error=None, header={})
    )
    assert project.model.is_model_valid


def test_create_uses_silent_storage_and_invalidates_only_local_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production mask creation bypasses direct model APIs and commits one local revision."""
    project = _project()
    history = _History()
    dispatched = []
    project.model.events.subscribe(dispatched.append)
    monkeypatch.setattr(
        project.model,
        "add_mask_definition",
        lambda _mask: pytest.fail("direct add_mask_definition is forbidden"),
    )

    result = MaskMutationUseCase().execute(
        project, CreateMaskRequest(mask=_mask("mask-1", "region-1")), history_recorder=history
    )

    assert result.changed
    assert project.model.find_mask("mask-1") == result.stored_mask
    assert [_revision(project, region_id) for region_id in ("region-1", "region-2")] == [1, 0]
    assert all(
        project.absorption_lines[line_id].needs_optimization
        for line_id in project.absorption_regions["region-1"].line_ids
    )
    assert not project.absorption_lines["line-region-2-0"].needs_optimization
    assert history.records[0][0] is MaskMutationKind.CREATE
    assert history.records[0][4:6] == (None, 0)
    assert history.records[0][6] == ("region-1",)
    assert dispatched == []


def test_create_assigns_empty_identifier_before_storage_and_history() -> None:
    """Generated create identity is shared by storage, result, and history."""
    project = _project()
    history = _History()
    requested = MaskDefinition(
        identifier="", label="", start_wavelength=100.0, end_wavelength=110.0, group_id="region-1"
    )

    result = MaskMutationUseCase().execute(
        project, CreateMaskRequest(mask=requested), history_recorder=history
    )

    assert requested.identifier == ""
    assert result.stored_mask is not None
    generated_id = result.stored_mask.identifier
    assert generated_id
    assert project.model.find_mask(generated_id) == result.stored_mask
    assert len(history.records) == 1
    _, recorded_id, before, after, before_index, after_index, _ = history.records[0]
    assert recorded_id == generated_id
    assert before is None
    assert after is not None
    assert after.identifier == generated_id
    assert before_index is None
    assert after_index == 0


def test_update_group_move_invalidates_old_and_new_once() -> None:
    """Mask reassignment advances both owning regions exactly once."""
    project = _project()
    project.model.add_mask_definition(_mask("mask-1", "region-1"))
    history = _History()

    result = MaskMutationUseCase().execute(
        project,
        UpdateMaskRequest(mask=_mask("mask-1", "region-2", start=120.0)),
        history_recorder=history,
    )

    assert result.changed
    assert result.impact.affected_region_ids == ("region-1", "region-2")
    assert [_revision(project, region_id) for region_id in ("region-1", "region-2")] == [1, 1]
    assert all(line.needs_optimization for line in project.absorption_lines.values())
    assert history.records[0][0] is MaskMutationKind.UPDATE
    assert history.records[0][4:6] == (0, 0)


def test_remove_records_exact_original_storage_index() -> None:
    """Forward delete history carries the removed mask's original order index."""
    project = _project()
    first = project.model.add_mask_definition(_mask("mask-1", "region-1"))
    removed = project.model.add_mask_definition(_mask("mask-2", "region-1", start=120.0))
    third = project.model.add_mask_definition(_mask("mask-3", "region-1", start=140.0))
    history = _History()

    result = MaskMutationUseCase().execute(
        project, RemoveMaskRequest(mask_id=removed.identifier), history_recorder=history
    )

    assert result.changed is True
    assert project.model.mask_definitions == (first, third)
    assert history.records[0][4:6] == (1, None)


def test_equal_update_is_complete_no_change_without_history_or_observers() -> None:
    """An equal upsert preserves project, history scope, and observers exactly."""
    project = _project()
    mask = project.model.add_mask_definition(_mask("mask-1", "region-1"))
    history = _History()
    modified_before = project.modified
    masks_before = project.model.mask_definitions
    dispatched = []
    project.model.events.subscribe(dispatched.append)

    result = MaskMutationUseCase().execute(
        project, UpdateMaskRequest(mask=mask), history_recorder=history
    )

    assert not result.changed
    assert project.model.mask_definitions == masks_before
    assert [_revision(project, region_id) for region_id in ("region-1", "region-2")] == [0, 0]
    assert project.modified == modified_before
    assert history.scope_entries == 0
    assert history.records == []
    assert dispatched == []


def test_missing_delete_is_complete_no_change() -> None:
    """Deleting an absent mask does not enter the scientific transaction."""
    project = _project()
    history = _History()
    modified_before = project.modified

    result = MaskMutationUseCase().execute(
        project, RemoveMaskRequest(mask_id="missing"), history_recorder=history
    )

    assert not result.changed
    assert project.modified == modified_before
    assert history.scope_entries == 0
    assert history.records == []


def test_dangling_new_group_is_rejected_before_mask_storage() -> None:
    """A mask can never commit a reference to a missing region."""
    project = _project()
    original = project.model.add_mask_definition(_mask("mask-1", "region-1"))
    history = _History()
    modified_before = project.modified

    with pytest.raises(ValueError, match="not found"):
        MaskMutationUseCase().execute(
            project,
            UpdateMaskRequest(mask=original.with_group_id("missing")),
            history_recorder=history,
        )

    assert project.model.mask_definitions == (original,)
    assert project.modified == modified_before
    assert history.records == []


def test_history_failure_restores_mask_order_cache_artifact_flags_and_modified() -> None:
    """A failed mask history record restores all project and model transaction facts."""
    project = _project()
    first = project.model.add_mask_definition(_mask("mask-1", "region-1"))
    removed = project.model.add_mask_definition(_mask("mask-2", "region-1", start=120.0))
    third = project.model.add_mask_definition(_mask("mask-3", "region-1", start=140.0))
    _make_model_valid(project)
    AnalysisArtifactStoreUseCase().record_artifact(
        project, "region-1", FitSummary(chi_squared=1.0)
    )
    state_before = project.region_analysis_state("region-1")
    modified_before = datetime(2020, 1, 1, tzinfo=UTC)
    project.modified = modified_before
    history = _History(fail=True)

    with pytest.raises(RuntimeError, match="mask history failed"):
        MaskMutationUseCase().execute(
            project, RemoveMaskRequest(mask_id=removed.identifier), history_recorder=history
        )

    assert project.model.mask_definitions == (first, removed, third)
    assert project.model.is_model_valid
    assert project.region_analysis_state("region-1") == state_before
    assert all(not line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified == modified_before
    assert history.records == []


def test_post_commit_notification_failure_does_not_revert_mask_or_revision() -> None:
    """An isolated mask observer failure reaches later listeners after commit."""
    project = _project()
    history = _History()
    result = MaskMutationUseCase().execute(
        project, CreateMaskRequest(mask=_mask("mask-1", "region-1")), history_recorder=history
    )
    modified_after_commit = project.modified

    def fail_observer(change_set: object) -> None:
        _ = change_set
        raise RuntimeError("mask observer failed")

    project.model.events.subscribe(fail_observer)
    later_events: list[object] = []
    project.model.events.subscribe(later_events.append)
    project.model.notify_mask_storage_changed()

    assert result.changed
    assert project.model.find_mask("mask-1") is not None
    assert _revision(project, "region-1") == 1
    assert project.modified == modified_after_commit
    assert len(history.records) == 1
    assert len(later_events) == 1


def test_partial_mask_storage_failure_restores_exact_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A storage exception after insertion restores order, validity, and project facts."""
    project = _project()
    existing = project.model.add_mask_definition(_mask("existing", "region-1"))
    _make_model_valid(project)
    modified_before = project.modified
    original_create = project.model.create_mask_definition_for_transaction

    def fail_after_create(mask: MaskDefinition) -> MaskDefinition:
        original_create(mask)
        raise RuntimeError("mask storage failed")

    monkeypatch.setattr(project.model, "create_mask_definition_for_transaction", fail_after_create)

    with pytest.raises(RuntimeError, match="mask storage failed"):
        MaskMutationUseCase().execute(
            project, CreateMaskRequest(mask=_mask("new", "region-1")), history_recorder=_History()
        )

    assert project.model.mask_definitions == (existing,)
    assert project.model.is_model_valid
    assert _revision(project, "region-1") == 0
    assert all(not line.needs_optimization for line in project.absorption_lines.values())
    assert project.modified == modified_before


def test_same_group_update_deduplicates_revision() -> None:
    """A local mask edit advances its owning region exactly once."""
    project = _project()
    project.model.add_mask_definition(_mask("mask-1", "region-1"))

    result = MaskMutationUseCase().execute(
        project,
        UpdateMaskRequest(mask=_mask("mask-1", "region-1", start=130.0)),
        history_recorder=_History(),
    )

    assert result.impact.affected_region_ids == ("region-1",)
    assert _revision(project, "region-1") == 1
