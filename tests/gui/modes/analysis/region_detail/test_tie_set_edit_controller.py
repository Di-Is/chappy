"""Tests for the optimize tie set share/remove controller."""

from __future__ import annotations

import contextlib

import pytest

from chappy.application.history.snapshot_mapping import tie_set_snapshot
from chappy.application.optimize import OptimizeParameterMutationUseCase, TieSetEditUseCase
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.atomic_data import AtomicLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import FULL_TIE_MASK, ParameterTieSet
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum_model import SpectrumModel
from chappy.gui.modes.analysis.region_detail.tie_set_edit_controller import (
    OptimizeTieSetEditController,
)

_TOLERANCE = 5e-5


def _atomic_line(species: str) -> AtomicLine:
    """Build an atomic line with the given species."""
    return AtomicLine(
        line_identifier=f"{species}_2796",
        species=species,
        wavelength_angstrom=2796.352,
        oscillator_strength=0.6123,
        gamma_value=2.6e8,
        multiplet_id="doublet",
    )


def _component(
    name: str, *, redshift: float = 1.0, species: str | None = "Mg II"
) -> AbsorberComponent:
    """Build an absorber component, optionally attaching an atomic line."""
    component = AbsorberComponent(name=name, redshift=redshift)
    if species is not None:
        component.atomic_line = _atomic_line(species)
    return component


class _Port:
    """Tie set edit port test double."""

    def __init__(self, model: SpectrumModel) -> None:
        self.project = SpectroscopyProject()
        self.project.model = model
        self.confirm_result = True
        self.confirm_calls: list[tuple[float, float]] = []
        self.created: list[tuple[str, int, object]] = []
        self.removed: list[tuple[tuple[str, ...], int, int, int]] = []
        self.refresh_count = 0
        self.fail_create_record = False
        self.fail_remove_record = False
        self.atomic_entries = 0

    def tie_set_edit_project(self) -> SpectroscopyProject | None:
        """Return the configured project."""
        return self.project

    def confirm_tie_set_redshift_divergence(
        self, max_delta_z: float, adopted_redshift: float
    ) -> bool:
        """Record the confirmation prompt and return the configured answer."""
        self.confirm_calls.append((max_delta_z, adopted_redshift))
        return self.confirm_result

    def record_tie_set_created(
        self,
        uid: str,
        before_component_states: tuple,
        after_tie_set: object,
        after_tie_set_index: int,
    ) -> None:
        """Record a tie set creation call."""
        assert after_tie_set_index >= 0
        if self.fail_create_record:
            raise RuntimeError("injected tie create history failure")
        self.created.append((uid, len(before_component_states), after_tie_set))

    def record_tie_set_removed(
        self,
        uids: tuple[str, ...],
        before_tie_sets: tuple,
        before_tie_set_indices: tuple[int, ...],
        after_tie_sets: tuple,
        after_tie_set_indices: tuple[int, ...],
        after_component_states: tuple,
    ) -> None:
        """Record a tie set removal call."""
        if self.fail_remove_record:
            raise RuntimeError("injected tie remove history failure")
        assert len(before_tie_sets) == len(before_tie_set_indices)
        assert len(after_tie_sets) == len(after_tie_set_indices)
        self.removed.append(
            (uids, len(before_tie_sets), len(after_tie_sets), len(after_component_states))
        )

    def refresh_after_tie_set_edit(self) -> None:
        """Record a refresh call."""
        self.refresh_count += 1

    @contextlib.contextmanager
    def tie_set_history_atomic_recording(self):
        """Record one atomic history boundary."""
        self.atomic_entries += 1
        yield


def _add_region(project: SpectroscopyProject, region_id: str) -> AbsorptionLine:
    """Add one analysis-capable region with a fresh line."""
    line = AbsorptionLine(
        line_id=f"line-{region_id}",
        species="Mg II",
        rest_wavelength=2796.352,
        center_z=1.2,
        window_kms=150.0,
        region_id=region_id,
        multiplet_label="",
        transition_name="Mg II",
        oscillator_strength=0.6,
        gamma_value=2.6e8,
        needs_optimization=False,
    )
    project.absorption_lines[line.line_id] = line
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=[line.line_id]
    )
    return line


def _controller(
    port: _Port, mutation: OptimizeParameterMutationUseCase | None = None
) -> OptimizeTieSetEditController:
    """Build a tie set edit controller wired to the given port."""
    usecase = TieSetEditUseCase(
        redshift_tolerance=_TOLERANCE,
        parameter_mutation=mutation or OptimizeParameterMutationUseCase(),
    )
    return OptimizeTieSetEditController(usecase=usecase, port=port)


def test_can_share_redshift_requires_two_untied_components() -> None:
    """Redshift sharing needs two or more untied components."""
    controller = _controller(_Port(SpectrumModel()))
    untied_pair = (_component("a"), _component("b"))
    single = (_component("a"),)

    assert controller.can_share_redshift(untied_pair) is True
    assert controller.can_share_redshift(single) is False


def test_can_share_redshift_accepts_full_tie_set_as_external_unit() -> None:
    """A full-mask tie set can join redshift sharing as one external unit."""
    tie_set = ParameterTieSet("multiplet-1")
    tied = _component("a")
    tie_set.add_component(tied)
    tie_set.add_component(_component("b"))
    controller = _controller(_Port(SpectrumModel()))

    assert controller.can_share_redshift((tied, _component("c"))) is True


def test_can_share_redshift_rejects_partial_tie_set_selection() -> None:
    """A partial-mask tie set cannot be nested into another external share."""
    tie_set = ParameterTieSet("partial-1", mask=frozenset({"redshift"}))
    tied = _component("a")
    tie_set.add_component(tied)
    tie_set.add_component(_component("b"))
    controller = _controller(_Port(SpectrumModel()))

    assert controller.can_share_redshift((tied, _component("c"))) is False


def test_can_share_redshift_and_b_matches_can_share_redshift() -> None:
    """Redshift-and-b sharing follows the same enable condition as redshift sharing."""
    controller = _controller(_Port(SpectrumModel()))
    untied_pair = (_component("a"), _component("b"))
    single = (_component("a"),)

    assert controller.can_share_redshift_and_b(untied_pair) is True
    assert controller.can_share_redshift_and_b(single) is False

    tie_set = ParameterTieSet("multiplet-1")
    tied = _component("a")
    tie_set.add_component(tied)
    tie_set.add_component(_component("b"))
    assert controller.can_share_redshift_and_b((tied, _component("c"))) is True


def test_can_share_all_parameters_requires_same_species() -> None:
    """Full sharing needs untied components of the same ion."""
    controller = _controller(_Port(SpectrumModel()))
    same_ion = (_component("a", species="Mg II"), _component("b", species="Mg II"))
    cross_ion = (_component("a", species="Mg II"), _component("b", species="Fe II"))

    assert controller.can_share_all_parameters(same_ion) is True
    assert controller.can_share_all_parameters(cross_ion) is False


def test_can_remove_from_shared_group_requires_a_tied_component() -> None:
    """Removal requires at least one tied component in the selection."""
    tie_set = ParameterTieSet("multiplet-1")
    tied = _component("a")
    tie_set.add_component(tied)
    tie_set.add_component(_component("b"))
    controller = _controller(_Port(SpectrumModel()))

    assert controller.can_remove_from_shared_group((tied, _component("c"))) is True
    assert controller.can_remove_from_shared_group((_component("c"), _component("d"))) is False


def test_share_redshift_creates_tie_set_and_records_undo() -> None:
    """Sharing z creates a user tie set and records its creation."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)
    components = (_component("a", redshift=1.2), _component("b", redshift=1.2))

    controller.share_redshift(components)

    assert len(port.created) == 1
    uid, before_count, _snapshot = port.created[0]
    assert uid == components[0].tie_set.uid
    assert before_count == 2
    assert components[0].tie_set is not None
    assert components[0].tie_set is components[1].tie_set
    assert components[0].tie_set.mask == frozenset({"redshift"})
    assert port.refresh_count == 1
    assert port.atomic_entries == 1


def test_share_redshift_and_b_creates_tie_set_and_records_undo() -> None:
    """Sharing z and b creates a user tie set masked to redshift and b_parameter."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)
    components = (_component("a", redshift=1.2), _component("b", redshift=1.2))

    controller.share_redshift_and_b(components)

    assert len(port.created) == 1
    uid, before_count, _snapshot = port.created[0]
    assert uid == components[0].tie_set.uid
    assert before_count == 2
    assert components[0].tie_set is not None
    assert components[0].tie_set is components[1].tie_set
    assert components[0].tie_set.mask == frozenset({"redshift", "b_parameter"})
    assert port.refresh_count == 1


def test_share_redshift_and_b_attaches_full_tie_set_as_external_unit() -> None:
    """Sharing z and b can attach a full-mask tie set without changing direct ownership."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)
    multiplet_components = (
        _component("mg-2796", redshift=1.2),
        _component("mg-2803", redshift=1.2),
    )
    direct = _component("fe-2600", redshift=1.2)
    inner = ParameterTieSet("multiplet-1")
    for component in multiplet_components:
        inner.add_component(component)
        model.add_component(component)
    model.add_tie_set(inner)
    model.add_component(direct)

    controller.share_redshift_and_b((multiplet_components[0], direct))

    assert len(port.created) == 1
    _uid, before_count, snapshot = port.created[0]
    assert before_count == 3
    outer = direct.tie_set
    assert isinstance(outer, ParameterTieSet)
    assert inner.parent_tie is outer
    assert outer.member_uids == {inner.uid}
    assert multiplet_components[0].tie_set is inner
    assert snapshot.member_uids == (inner.uid,)


def test_share_all_parameters_creates_full_mask_tie_set() -> None:
    """Sharing all parameters creates a tie set covering the full mask."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)
    components = (_component("a", redshift=1.2), _component("b", redshift=1.2))

    controller.share_all_parameters(components)

    assert len(port.created) == 1
    assert components[0].tie_set is not None
    assert components[0].tie_set.mask == FULL_TIE_MASK


def test_share_redshift_needs_confirmation_for_divergent_redshifts() -> None:
    """A divergent redshift selection prompts for confirmation before creating."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)
    components = (_component("a", redshift=1.0), _component("b", redshift=1.001))

    controller.share_redshift(components)

    assert len(port.confirm_calls) == 1
    max_delta_z, adopted_redshift = port.confirm_calls[0]
    assert abs(max_delta_z - 0.001) < 1e-12
    assert adopted_redshift == 1.0
    assert len(port.created) == 1
    assert components[0].tie_set is not None


def test_share_redshift_confirmation_declined_does_not_create() -> None:
    """Declining the divergence confirmation leaves components untied."""
    model = SpectrumModel()
    port = _Port(model)
    port.confirm_result = False
    controller = _controller(port)
    components = (_component("a", redshift=1.0), _component("b", redshift=1.001))

    controller.share_redshift(components)

    assert len(port.confirm_calls) == 1
    assert port.created == []
    assert components[0].tie_set is None
    assert port.refresh_count == 0
    assert port.atomic_entries == 1


def test_remove_from_shared_group_unbinds_and_records_undo() -> None:
    """Removing a component from its tie set records the removal in history."""
    model = SpectrumModel()
    components = (_component("a"), _component("b"), _component("c"))
    tie_set = ParameterTieSet("multiplet-1")
    for component in components:
        tie_set.add_component(component)
    model.add_tie_set(tie_set)
    port = _Port(model)
    controller = _controller(port)

    controller.remove_from_shared_group((components[0],))

    assert components[0].tie_set is None
    assert len(port.removed) == 1
    uids, before_count, after_count, after_state_count = port.removed[0]
    assert uids == (tie_set.uid,)
    assert before_count == 1
    assert after_count == 1
    assert after_state_count >= 1
    assert port.refresh_count == 1


def test_remove_from_external_group_detaches_inner_tie_set_and_records_undo() -> None:
    """External removal detaches the selected multiplet unit from its parent tie set."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)
    inner_first = _component("inner-first", redshift=1.2)
    inner_second = _component("inner-second", redshift=1.2)
    direct = _component("direct", redshift=1.2)
    inner = ParameterTieSet("inner")
    inner.add_component(inner_first)
    inner.add_component(inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)
    for component in (inner_first, inner_second, direct):
        model.add_component(component)
    model.add_tie_set(inner)
    model.add_tie_set(outer)

    controller.remove_from_external_group((inner_first,))

    assert inner.parent_tie is None
    assert inner_first.tie_set is inner
    assert inner_second.tie_set is inner
    assert len(port.removed) == 1
    uids, before_count, after_count, after_component_count = port.removed[0]
    assert set(uids) == {outer.uid, inner.uid}
    assert before_count == 2
    assert after_count == 1
    assert after_component_count >= 2


def test_remove_from_shared_group_no_op_when_nothing_tied() -> None:
    """Removal against an untied selection is rejected without recording anything."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)

    controller.remove_from_shared_group((_component("a"),))

    assert port.removed == []
    assert port.refresh_count == 0


def test_tie_set_snapshot_reused_by_create_recording() -> None:
    """The snapshot passed to history recording matches the created tie set."""
    model = SpectrumModel()
    port = _Port(model)
    controller = _controller(port)
    components = (_component("a", redshift=1.2), _component("b", redshift=1.2))

    controller.share_redshift(components)

    _uid, _before_count, snapshot = port.created[0]
    tie_set = components[0].tie_set
    assert tie_set is not None
    assert snapshot == tie_set_snapshot(tie_set)


def test_tie_create_history_failure_restores_exact_topology_and_freshness() -> None:
    """A create-history failure restores untied parameters and every region revision."""
    model = SpectrumModel()
    port = _Port(model)
    first = _component("a", redshift=1.2)
    second = _component("b", redshift=1.2)
    model.add_component(first)
    model.add_component(second)
    lines = (_add_region(port.project, "region-1"), _add_region(port.project, "region-2"))
    port.fail_create_record = True

    with pytest.raises(RuntimeError, match="injected tie create history failure"):
        _controller(port).share_redshift((first, second))

    assert first.tie_set is None
    assert second.tie_set is None
    assert first.parameters["redshift"] is not second.parameters["redshift"]
    assert tuple(model.iter_tie_sets()) == ()
    assert all(
        port.project.region_analysis_state(region_id).current_revision == AnalysisRevision(0)
        for region_id in ("region-1", "region-2")
    )
    assert all(not line.needs_optimization for line in lines)
    assert port.refresh_count == 0


def test_tie_remove_history_failure_restores_nested_topology() -> None:
    """A remove-history failure restores parent attachment and shared parameter identity."""
    model = SpectrumModel()
    port = _Port(model)
    inner_first = _component("inner-first", redshift=1.2)
    inner_second = _component("inner-second", redshift=1.2)
    direct = _component("direct", redshift=1.2)
    inner = ParameterTieSet("inner")
    inner.add_component(inner_first)
    inner.add_component(inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)
    for component in (inner_first, inner_second, direct):
        model.add_component(component)
    model.add_tie_set(inner)
    model.add_tie_set(outer)
    snapshots_before = tuple(tie_set_snapshot(tie_set) for tie_set in model.iter_tie_sets())
    port.fail_remove_record = True

    with pytest.raises(RuntimeError, match="injected tie remove history failure"):
        _controller(port).remove_from_external_group((inner_first,))

    snapshots_after = tuple(tie_set_snapshot(tie_set) for tie_set in model.iter_tie_sets())
    assert snapshots_after == snapshots_before
    restored_inner = inner_first.tie_set
    assert isinstance(restored_inner, ParameterTieSet)
    restored_outer = restored_inner.parent_tie
    assert isinstance(restored_outer, ParameterTieSet)
    assert direct.tie_set is restored_outer
    assert inner_first.parameters["redshift"] is direct.parameters["redshift"]
    assert port.refresh_count == 0


def test_tie_observer_failure_keeps_commit_and_all_regions_stale_once() -> None:
    """An isolated observer failure keeps the commit and reaches later listeners."""
    model = SpectrumModel()
    port = _Port(model)
    first = _component("a", redshift=1.2)
    second = _component("b", redshift=1.2)
    model.add_component(first)
    model.add_component(second)
    lines = (_add_region(port.project, "region-1"), _add_region(port.project, "region-2"))
    later_events: list[object] = []

    def fail_observer(_changes: object) -> None:
        raise RuntimeError("injected tie observer failure")

    model.events.subscribe(fail_observer)
    model.events.subscribe(later_events.append)

    _controller(port).share_redshift((first, second))

    assert first.tie_set is not None
    assert first.tie_set is second.tie_set
    assert len(port.created) == 1
    assert all(
        port.project.region_analysis_state(region_id).current_revision == AnalysisRevision(1)
        for region_id in ("region-1", "region-2")
    )
    assert all(line.needs_optimization for line in lines)
    assert len(later_events) == 1
    assert port.refresh_count == 1
