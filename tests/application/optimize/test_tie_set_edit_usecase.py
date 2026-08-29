"""Tests for the parameter tie set edit use case."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.application.optimize import (
    OptimizeParameterMutationUseCase,
    TieSetCreated,
    TieSetCreationNeedsConfirmation,
    TieSetCreationRejected,
    TieSetEditRejectionReason,
    TieSetEditUseCase,
    TieSetRemovalRejected,
)
from chappy.core.atomic_data import AtomicLine
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import FULL_TIE_MASK, ParameterTieSet
from chappy.core.spectrum_model import SpectrumModel

if TYPE_CHECKING:
    from chappy.core.components.tie_set import TieParameterName

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


def _usecase(mutation: OptimizeParameterMutationUseCase | None = None) -> TieSetEditUseCase:
    """Build the tie set edit use case with the multiplet redshift tolerance."""
    return TieSetEditUseCase(
        redshift_tolerance=_TOLERANCE,
        parameter_mutation=mutation or OptimizeParameterMutationUseCase(),
    )


def _create(
    model: SpectrumModel,
    components: tuple[AbsorberComponent, ...],
    mask: frozenset[TieParameterName] = FULL_TIE_MASK,
    *,
    usecase: TieSetEditUseCase | None = None,
) -> TieSetCreated:
    """Create a tie set and assert success."""
    result = (usecase or _usecase()).create_tie_set(model, components, mask)
    assert isinstance(result, TieSetCreated)
    return result


def test_create_rejects_unsupported_mask() -> None:
    """Only the three approved masks are accepted."""
    components = (_component("a"), _component("b"))

    result = _usecase().create_tie_set(SpectrumModel(), components, frozenset({"b_parameter"}))

    assert isinstance(result, TieSetCreationRejected)
    assert result.reason is TieSetEditRejectionReason.INVALID_MASK


def test_create_rejects_fewer_than_two_components() -> None:
    """A tie set needs at least two components."""
    result = _usecase().create_tie_set(SpectrumModel(), (_component("a"),), FULL_TIE_MASK)

    assert isinstance(result, TieSetCreationRejected)
    assert result.reason is TieSetEditRejectionReason.TOO_FEW_COMPONENTS


def test_create_rejects_component_already_in_tie_set() -> None:
    """Components already tied elsewhere cannot join a new tie set."""
    tied_a, tied_b, free = _component("a"), _component("b"), _component("c")
    existing = ParameterTieSet("existing")
    existing.add_component(tied_a)
    existing.add_component(tied_b)

    result = _usecase().create_tie_set(SpectrumModel(), (tied_a, free), FULL_TIE_MASK)

    assert isinstance(result, TieSetCreationRejected)
    assert result.reason is TieSetEditRejectionReason.ALREADY_TIED


def test_create_full_mask_rejects_mixed_species() -> None:
    """Sharing column density across different ions is rejected."""
    components = (_component("a", species="Mg II"), _component("b", species="Fe II"))

    result = _usecase().create_tie_set(SpectrumModel(), components, FULL_TIE_MASK)

    assert isinstance(result, TieSetCreationRejected)
    assert result.reason is TieSetEditRejectionReason.MIXED_SPECIES


def test_create_full_mask_rejects_component_without_atomic_line() -> None:
    """Unknown species cannot join a column-density-sharing tie set."""
    components = (_component("a", species="Mg II"), _component("b", species=None))

    result = _usecase().create_tie_set(SpectrumModel(), components, FULL_TIE_MASK)

    assert isinstance(result, TieSetCreationRejected)
    assert result.reason is TieSetEditRejectionReason.MIXED_SPECIES


def test_create_redshift_only_mask_allows_mixed_species() -> None:
    """A redshift-only tie set may span different ions."""
    components = (_component("a", species="Mg II"), _component("b", species="Fe II"))

    result = _create(SpectrumModel(), components, frozenset({"redshift"}))

    assert result.tie_set.mask == frozenset({"redshift"})


def test_create_requires_confirmation_for_divergent_redshifts() -> None:
    """Redshift spread beyond tolerance asks for confirmation."""
    components = (_component("a", redshift=1.0), _component("b", redshift=1.001))

    result = _usecase().create_tie_set(SpectrumModel(), components, FULL_TIE_MASK)

    assert isinstance(result, TieSetCreationNeedsConfirmation)
    assert result.adopted_redshift == 1.0
    assert abs(result.max_delta_z - 0.001) < 1e-12


def test_create_with_confirmed_divergence_adopts_first_redshift() -> None:
    """Confirmed divergent creation seeds masters from the first component."""
    model = SpectrumModel()
    components = (_component("a", redshift=1.0), _component("b", redshift=1.001))

    result = _usecase().create_tie_set(
        model, components, FULL_TIE_MASK, confirmed_redshift_divergence=True
    )

    assert isinstance(result, TieSetCreated)
    assert result.tie_set.shared_parameters["redshift"].value == 1.0
    assert components[1].get_parameter_value("redshift") == 1.0


def test_create_tie_set_adopts_first_selected_direct_fixed_state() -> None:
    """A direct first selection should seed the shared fixed state."""
    model = SpectrumModel()
    first = _component("a", redshift=1.0)
    second = _component("b", redshift=1.0)
    first.parameters["redshift"].fixed = True
    second.parameters["redshift"].fixed = False

    result = _create(model, (first, second), frozenset({"redshift"}))

    assert result.tie_set.shared_parameters["redshift"].fixed is True
    assert first.parameters["redshift"].fixed is True
    assert second.parameters["redshift"].fixed is True


def test_create_external_share_adopts_first_selected_inner_redshift() -> None:
    """A leading inner selection provides the adopted redshift over a later direct one."""
    model = SpectrumModel()
    inner = _create(model, (_component("a", redshift=1.5), _component("b", redshift=1.5))).tie_set
    direct = _component("c", redshift=1.0)

    result = _usecase().create_tie_set(
        model, (inner.components[0], direct), frozenset({"redshift"})
    )

    assert isinstance(result, TieSetCreationNeedsConfirmation)
    assert result.adopted_redshift == 1.5


def test_create_external_share_confirmed_seeds_first_selected_inner_redshift() -> None:
    """Confirmed creation from a leading inner selection seeds masters with its redshift."""
    model = SpectrumModel()
    inner = _create(model, (_component("a", redshift=1.5), _component("b", redshift=1.5))).tie_set
    direct = _component("c", redshift=1.0)

    result = _usecase().create_tie_set(
        model,
        (inner.components[0], direct),
        frozenset({"redshift"}),
        confirmed_redshift_divergence=True,
    )

    assert isinstance(result, TieSetCreated)
    assert result.tie_set.shared_parameters["redshift"].value == 1.5
    assert direct.get_parameter_value("redshift") == 1.5
    assert inner.components[1].get_parameter_value("redshift") == 1.5


def test_create_external_share_adopts_first_selected_inner_fixed_state() -> None:
    """A leading nested tie set should seed the external shared fixed state."""
    model = SpectrumModel()
    inner = _create(model, (_component("a"), _component("b"))).tie_set
    inner.fix_parameter("redshift", fixed=True)
    direct = _component("c")
    direct.parameters["redshift"].fixed = False

    result = _create(model, (inner.components[0], direct), frozenset({"redshift"}))

    assert result.tie_set.shared_parameters["redshift"].fixed is True
    assert inner.components[0].parameters["redshift"].fixed is True
    assert inner.components[1].parameters["redshift"].fixed is True
    assert direct.parameters["redshift"].fixed is True


def test_create_external_share_adopts_first_selected_direct_redshift() -> None:
    """A leading direct selection provides the adopted redshift over a later inner one."""
    model = SpectrumModel()
    inner = _create(model, (_component("a", redshift=1.5), _component("b", redshift=1.5))).tie_set
    direct = _component("c", redshift=1.0)

    result = _usecase().create_tie_set(
        model, (direct, inner.components[0]), frozenset({"redshift"})
    )

    assert isinstance(result, TieSetCreationNeedsConfirmation)
    assert result.adopted_redshift == 1.0


def test_create_success_binds_components_and_registers_tie_set() -> None:
    """Successful creation binds all components to user-origin masters."""
    model = SpectrumModel()
    first = _component("a", redshift=1.2)
    second = _component("b", redshift=1.2)

    result = _create(model, (first, second))

    tie_set = result.tie_set
    assert tie_set.origin == "user"
    assert tie_set.tie_id.startswith("user-")
    assert tie_set in tuple(model.iter_tie_sets())
    assert first.tie_set is tie_set
    assert second.tie_set is tie_set
    assert first.parameters["redshift"] is tie_set.shared_parameters["redshift"]
    assert second.parameters["redshift"] is tie_set.shared_parameters["redshift"]
    assert tie_set.shared_parameters["redshift"].value == 1.2
    assert len(result.before_component_states) == 2


def test_create_from_only_tie_sets_adopts_first_inner_master_values() -> None:
    """Sharing existing full tie sets without direct components keeps their current values."""
    model = SpectrumModel()
    first = _create(model, (_component("a", redshift=1.5), _component("b", redshift=1.5))).tie_set
    second = _create(model, (_component("c", redshift=1.5), _component("d", redshift=1.5))).tie_set
    first.set_shared_parameter("b_parameter", 25.0)

    result = _create(
        model, (first.components[0], second.components[0]), frozenset({"redshift", "b_parameter"})
    )

    assert result.tie_set.shared_parameters["redshift"].value == 1.5
    assert result.tie_set.shared_parameters["b_parameter"].value == 25.0
    assert first.components[0].get_parameter_value("redshift") == 1.5
    assert second.components[0].get_parameter_value("redshift") == 1.5
    assert first.components[0].get_parameter_value("b_parameter") == 25.0


def test_remove_rejects_when_no_component_is_tied() -> None:
    """Removal is rejected when no selected component belongs to a tie set."""
    result = _usecase().remove_from_tie_set(SpectrumModel(), (_component("a"),))

    assert isinstance(result, TieSetRemovalRejected)
    assert result.reason is TieSetEditRejectionReason.NOT_TIED


def test_partial_removal_keeps_tie_set_and_converts_origin() -> None:
    """Removing one member of three keeps the tie set alive as user-origin."""
    model = SpectrumModel()
    components = (_component("a"), _component("b"), _component("c"))
    tie_set = ParameterTieSet("multiplet-1")
    for component in components:
        tie_set.add_component(component)
    model.add_tie_set(tie_set)
    assert tie_set.origin == "multiplet"

    result = _usecase().remove_from_tie_set(model, (components[0],))

    assert not isinstance(result, TieSetRemovalRejected)
    assert len(result) == 1
    applied = result[0]
    assert applied.before_snapshot.origin == "multiplet"
    assert applied.after_snapshot is not None
    assert applied.after_snapshot.origin == "user"
    assert tie_set.origin == "user"
    assert tie_set in tuple(model.iter_tie_sets())
    assert components[0].tie_set is None
    assert components[1].tie_set is tie_set


def test_removal_gives_unbound_component_fresh_parameters() -> None:
    """Unbound components copy master values with fixed flags and zero error."""
    model = SpectrumModel()
    components = (_component("a"), _component("b"), _component("c"))
    tie_set = ParameterTieSet("multiplet-1")
    for component in components:
        tie_set.add_component(component)
    model.add_tie_set(tie_set)
    tie_set.set_shared_parameter("redshift", 2.5)
    tie_set.fix_parameter("b_parameter", fixed=True)
    tie_set.shared_parameters["redshift"].error = 0.01

    _usecase().remove_from_tie_set(model, (components[0],))

    removed = components[0]
    assert removed.parameters["redshift"] is not tie_set.shared_parameters["redshift"]
    assert removed.parameters["redshift"].value == 2.5
    assert removed.parameters["redshift"].error == 0.0
    assert removed.parameters["b_parameter"].fixed is True


def test_removal_down_to_one_component_dissolves_tie_set() -> None:
    """Leaving fewer than two members dissolves the tie set entirely."""
    model = SpectrumModel()
    components = (_component("a"), _component("b"))
    tie_set = ParameterTieSet("multiplet-1")
    for component in components:
        tie_set.add_component(component)
    model.add_tie_set(tie_set)

    result = _usecase().remove_from_tie_set(model, (components[0],))

    assert not isinstance(result, TieSetRemovalRejected)
    applied = result[0]
    assert applied.after_snapshot is None
    assert tuple(model.iter_tie_sets()) == ()
    assert components[0].tie_set is None
    assert components[1].tie_set is None
    assert len(applied.after_component_states) == 2


def test_removing_only_direct_component_dissolves_external_parent() -> None:
    """Removing the sole direct member leaves one participation unit, dissolving the parent."""
    model = SpectrumModel()
    inner_a, inner_b, direct = _component("a"), _component("b"), _component("c")
    inner = _create(model, (inner_a, inner_b)).tie_set
    outer = _create(model, (direct, inner_a), frozenset({"redshift"})).tie_set

    result = _usecase().remove_from_tie_set(model, (direct,))

    assert not isinstance(result, TieSetRemovalRejected)
    assert result[0].after_snapshot is None
    assert outer not in tuple(model.iter_tie_sets())
    assert inner in tuple(model.iter_tie_sets())
    assert inner.parent_tie is None
    assert direct.tie_set is None
    assert inner_a.tie_set is inner
    assert inner_a.parameters["redshift"] is inner.shared_parameters["redshift"]


def test_dissolving_nested_inner_records_surviving_parent_snapshot() -> None:
    """Detaching an inner tie set from a surviving parent must be recorded for undo."""
    model = SpectrumModel()
    inner_a, inner_b = _component("a"), _component("b")
    direct_1, direct_2 = _component("c"), _component("d")
    inner = _create(model, (inner_a, inner_b)).tie_set
    outer = _create(model, (direct_1, direct_2, inner_a), frozenset({"redshift"})).tie_set

    result = _usecase().remove_from_tie_set(model, (inner_a,))

    assert not isinstance(result, TieSetRemovalRejected)
    parent_applied = next(applied for applied in result if applied.uid == outer.uid)
    assert inner.uid in parent_applied.before_snapshot.member_uids
    assert parent_applied.after_snapshot is not None
    assert inner.uid not in parent_applied.after_snapshot.member_uids
    assert inner not in tuple(model.iter_tie_sets())
    assert direct_1.tie_set is outer
    assert direct_2.tie_set is outer


def test_partial_removal_from_nested_inner_records_surviving_parent() -> None:
    """A nested inner that survives removal must still record its parent for undo."""
    model = SpectrumModel()
    inner_a, inner_b, inner_c = _component("a"), _component("b"), _component("c")
    direct = _component("d")
    inner = _create(model, (inner_a, inner_b, inner_c)).tie_set
    outer = _create(model, (direct, inner_a), frozenset({"redshift"})).tie_set

    result = _usecase().remove_from_tie_set(model, (inner_a,))

    assert not isinstance(result, TieSetRemovalRejected)
    parent_applied = next(applied for applied in result if applied.uid == outer.uid)
    assert inner.uid in parent_applied.before_snapshot.member_uids
    assert parent_applied.after_snapshot is not None
    assert inner.uid in parent_applied.after_snapshot.member_uids
    assert inner.parent_tie is outer
    assert inner_b.tie_set is inner
    assert inner_c.tie_set is inner
    assert inner_a.tie_set is None


def test_dissolving_nested_inner_records_dissolved_parent_snapshot() -> None:
    """Collapsing an inner tie set that dissolves its parent must record the parent."""
    model = SpectrumModel()
    inner_a, inner_b, direct = _component("a"), _component("b"), _component("c")
    inner = _create(model, (inner_a, inner_b)).tie_set
    outer = _create(model, (direct, inner_a), frozenset({"redshift"})).tie_set

    result = _usecase().remove_from_tie_set(model, (inner_a,))

    assert not isinstance(result, TieSetRemovalRejected)
    parent_applied = next(applied for applied in result if applied.uid == outer.uid)
    assert inner.uid in parent_applied.before_snapshot.member_uids
    assert parent_applied.after_snapshot is None
    assert tuple(model.iter_tie_sets()) == ()
    assert direct.tie_set is None
    assert inner_a.tie_set is None
    assert inner_b.tie_set is None


def test_detaching_two_inners_from_shared_parent_records_parent_once() -> None:
    """Detaching two inner tie sets from a surviving parent records the parent once."""
    model = SpectrumModel()
    direct_1, direct_2 = _component("d1"), _component("d2")
    inner_1 = _create(model, (_component("a"), _component("b"))).tie_set
    inner_2 = _create(model, (_component("c"), _component("e"))).tie_set
    outer = _create(
        model,
        (direct_1, direct_2, inner_1.components[0], inner_2.components[0]),
        frozenset({"redshift"}),
    ).tie_set

    result = _usecase().remove_from_parent_tie_set(
        model, (inner_1.components[0], inner_2.components[0])
    )

    assert not isinstance(result, TieSetRemovalRejected)
    parent_entries = [applied for applied in result if applied.uid == outer.uid]
    assert len(parent_entries) == 1
    parent_applied = parent_entries[0]
    assert {inner_1.uid, inner_2.uid} <= set(parent_applied.before_snapshot.member_uids)
    assert parent_applied.after_snapshot is not None
    assert inner_1.uid not in parent_applied.after_snapshot.member_uids
    assert inner_2.uid not in parent_applied.after_snapshot.member_uids
    assert inner_1.parent_tie is None
    assert inner_2.parent_tie is None
    assert direct_1.tie_set is outer
    assert direct_2.tie_set is outer


def test_collapsing_two_sibling_inners_records_shared_parent_once() -> None:
    """Collapsing two sibling inners under one surviving parent records it once."""
    model = SpectrumModel()
    direct_1, direct_2 = _component("d1"), _component("d2")
    inner_1_a, inner_1_b = _component("a"), _component("b")
    inner_2_a, inner_2_b = _component("c"), _component("e")
    inner_1 = _create(model, (inner_1_a, inner_1_b)).tie_set
    inner_2 = _create(model, (inner_2_a, inner_2_b)).tie_set
    outer = _create(
        model, (direct_1, direct_2, inner_1_a, inner_2_a), frozenset({"redshift"})
    ).tie_set

    result = _usecase().remove_from_tie_set(model, (inner_1_a, inner_2_a))

    assert not isinstance(result, TieSetRemovalRejected)
    parent_entries = [applied for applied in result if applied.uid == outer.uid]
    assert len(parent_entries) == 1
    parent_applied = parent_entries[0]
    assert {inner_1.uid, inner_2.uid} <= set(parent_applied.before_snapshot.member_uids)
    assert parent_applied.after_snapshot is not None
    assert inner_1.uid not in parent_applied.after_snapshot.member_uids
    assert inner_2.uid not in parent_applied.after_snapshot.member_uids
    assert direct_1.tie_set is outer
    assert direct_2.tie_set is outer


def test_removal_spanning_two_tie_sets_reports_each() -> None:
    """A selection across two tie sets produces one result per set."""
    model = SpectrumModel()
    first_members = (_component("a"), _component("b"), _component("c"))
    second_members = (_component("d"), _component("e"), _component("f"))
    first = ParameterTieSet("multiplet-1")
    second = ParameterTieSet("multiplet-2")
    for component in first_members:
        first.add_component(component)
    for component in second_members:
        second.add_component(component)
    model.add_tie_set(first)
    model.add_tie_set(second)

    result = _usecase().remove_from_tie_set(
        model, (first_members[0], second_members[0], _component("free"))
    )

    assert not isinstance(result, TieSetRemovalRejected)
    assert {applied.uid for applied in result} == {first.uid, second.uid}


def test_removal_isolates_tie_sets_that_share_a_tie_id() -> None:
    """Removing one member from each of two same-tie_id tie sets must not merge them."""
    model = SpectrumModel()
    first_members = (_component("a"), _component("b"), _component("c"))
    second_members = (_component("d"), _component("e"), _component("f"))
    first = ParameterTieSet("multiplet-1")
    second = ParameterTieSet("multiplet-1")
    for component in first_members:
        first.add_component(component)
    for component in second_members:
        second.add_component(component)
    model.add_tie_set(first)
    model.add_tie_set(second)

    result = _usecase().remove_from_tie_set(model, (first_members[0], second_members[0]))

    assert not isinstance(result, TieSetRemovalRejected)
    assert {applied.uid for applied in result} == {first.uid, second.uid}
    assert first in tuple(model.iter_tie_sets())
    assert second in tuple(model.iter_tie_sets())
    assert first_members[0].tie_set is None
    assert second_members[0].tie_set is None
    assert first_members[1].tie_set is first
    assert second_members[1].tie_set is second
    assert first_members[1].parameters["redshift"] is not second_members[1].parameters["redshift"]


def test_removal_marks_covering_factor_initialized_against_id_reuse() -> None:
    """Fresh covering factor parameters must not be re-forced to fixed."""
    mutation = OptimizeParameterMutationUseCase()
    usecase = _usecase(mutation)
    model = SpectrumModel()
    components = (_component("a"), _component("b"), _component("c"))
    tie_set = ParameterTieSet("multiplet-1")
    for component in components:
        tie_set.add_component(component)
    model.add_tie_set(tie_set)
    tie_set.fix_parameter("covering_factor", fixed=False)

    usecase.remove_from_tie_set(model, (components[0],))

    parameter = mutation.ensure_covering_factor_parameter(components[0])
    assert parameter is components[0].parameters["covering_factor"]
    assert parameter.fixed is False


def test_create_marks_shared_covering_factor_initialized() -> None:
    """The shared covering factor master keeps its state through ensure calls."""
    mutation = OptimizeParameterMutationUseCase()
    usecase = _usecase(mutation)
    model = SpectrumModel()
    components = (_component("a"), _component("b"))
    for component in components:
        component.parameters["covering_factor"].fixed = False

    result = _create(model, components, usecase=usecase)

    parameter = mutation.ensure_covering_factor_parameter(components[0])
    assert parameter is result.tie_set.shared_parameters["covering_factor"]
    assert parameter.fixed is False
