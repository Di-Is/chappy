"""Tests for optimize history adapter."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from chappy.application.history import (
    ComponentParameterState,
    MaskDefinitionSnapshot,
    component_parameter_state,
)
from chappy.application.optimize import MaskMutationKind, ModelDeletionHistorySnapshot
from chappy.core.components.absorber import AbsorberComponent
from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import OptimizeHistoryAdapter

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from chappy.core.components.tie_set import ParameterTieSet


@dataclass(slots=True)
class _RecordingBridge:
    """History bridge fake that records forwarded commands."""

    suppress_count: int = 0
    atomic_count: int = 0
    edit_calls: list[
        tuple[
            list[str],
            str,
            tuple[ComponentParameterState, ...],
            tuple[ComponentParameterState, ...],
            str | None,
        ]
    ] = field(default_factory=list)
    delete_calls: list[ModelDeletionHistorySnapshot] = field(default_factory=list)
    add_calls: list[tuple[dict[str, AbsorberComponent], tuple["ParameterTieSet", ...]]] = field(
        default_factory=list
    )
    mask_calls: list[
        tuple[
            MaskMutationKind,
            str,
            MaskDefinitionSnapshot | None,
            MaskDefinitionSnapshot | None,
            int | None,
            int | None,
            tuple[str, ...],
        ]
    ] = field(default_factory=list)

    def suppress_recording(self) -> AbstractContextManager[None]:
        """Record suppression and return a no-op context."""
        self.suppress_count += 1
        return contextlib.nullcontext()

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Record an atomic scientific recording request."""
        self.atomic_count += 1
        return contextlib.nullcontext()

    def record_model_edit_params(
        self,
        component_ids: list[str],
        param_name: str,
        before_states: tuple[ComponentParameterState, ...],
        after_states: tuple[ComponentParameterState, ...],
        region_id: str | None,
    ) -> None:
        """Record a parameter edit command."""
        self.edit_calls.append((component_ids, param_name, before_states, after_states, region_id))

    def record_model_delete_snapshot(self, snapshot: ModelDeletionHistorySnapshot) -> None:
        """Record a component deletion command."""
        self.delete_calls.append(snapshot)

    def record_model_add(
        self, components: dict[str, AbsorberComponent], tie_sets: tuple["ParameterTieSet", ...]
    ) -> None:
        """Record a component addition command."""
        self.add_calls.append((components, tie_sets))

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
        """Record one forwarded mask mutation."""
        self.mask_calls.append(
            (kind, mask_id, before, after, before_index, after_index, affected_region_ids)
        )


def test_adapter_noops_without_bridge() -> None:
    """Adapter should tolerate missing history bridge."""
    adapter = OptimizeHistoryAdapter()
    component = AbsorberComponent(component_id="component-1")

    with adapter.recording_suppressed():
        adapter.record_add({"line-1": component}, ())
        adapter.record_parameter_edit(
            ["component-1"],
            "redshift",
            (component_parameter_state(component),),
            (component_parameter_state(component),),
            "region-1",
        )


def test_scientific_atomic_recording_fails_without_bridge() -> None:
    """A scientific edit must fail before mutation when Undo is unavailable."""
    adapter = OptimizeHistoryAdapter()

    with pytest.raises(RuntimeError, match="connected history recorder"):
        adapter.atomic_recording()


def test_adapter_forwards_history_commands() -> None:
    """Adapter should forward typed optimize history commands."""
    adapter = OptimizeHistoryAdapter()
    bridge = _RecordingBridge()
    adapter.set_bridge(bridge)
    component = AbsorberComponent(component_id="component-1")
    before_state = (component_parameter_state(component),)
    after_state = (component_parameter_state(component),)
    delete_snapshot = ModelDeletionHistorySnapshot(
        components=(), component_indices=(), links=(), tie_sets=(), tie_set_indices=()
    )

    with adapter.recording_suppressed():
        pass
    with adapter.atomic_recording():
        pass
    adapter.record_parameter_edit(
        ["component-1"], "redshift", before_state, after_state, "region-1"
    )
    adapter.record_delete(delete_snapshot)
    adapter.record_add({"line-1": component}, ())
    mask_snapshot = MaskDefinitionSnapshot(
        identifier="mask-1",
        label="Mask 1",
        mode="range",
        start_wavelength=100.0,
        end_wavelength=110.0,
        center=105.0,
        half_width=5.0,
        note="",
        color="#abcdef",
        enabled=True,
        group_id="region-1",
    )
    adapter.record_mask_mutation(
        kind=MaskMutationKind.CREATE,
        mask_id="mask-1",
        before=None,
        after=mask_snapshot,
        before_index=None,
        after_index=0,
        affected_region_ids=("region-1",),
    )

    assert bridge.suppress_count == 1
    assert bridge.atomic_count == 1
    assert bridge.edit_calls == [
        (["component-1"], "redshift", before_state, after_state, "region-1")
    ]
    assert bridge.delete_calls == [delete_snapshot]
    assert bridge.add_calls == [({"line-1": component}, ())]
    assert bridge.mask_calls == [
        (MaskMutationKind.CREATE, "mask-1", None, mask_snapshot, None, 0, ("region-1",))
    ]
