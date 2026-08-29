from __future__ import annotations

import pytest

from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import (
    ParameterTieSet,
    effective_tie_set_for_parameter,
    participation_unit_count,
)
from chappy.core.events import ComponentChanged


def _component(
    component_id: str, *, redshift: float = 1.0, b_parameter: float = 10.0
) -> AbsorberComponent:
    """Create a deterministic absorber component."""
    return AbsorberComponent(
        component_id=component_id, redshift=redshift, b_parameter=b_parameter, column_density=13.0
    )


def _full_tie_set(tie_id: str, *components: AbsorberComponent) -> ParameterTieSet:
    """Create a full-mask tie set containing the supplied components."""
    tie_set = ParameterTieSet(tie_id)
    for component in components:
        tie_set.add_component(component)
    return tie_set


def test_add_component_fails_fast_when_required_covering_factor_is_missing() -> None:
    """A full tie set must not repair a corrupted absorber parameter mapping."""
    component = _component("component-1")
    del component.parameters["covering_factor"]
    tie_set = ParameterTieSet("full-1")

    with pytest.raises(KeyError, match="covering_factor"):
        tie_set.add_component(component)

    assert component not in tie_set.components
    assert "covering_factor" not in component.parameters


def test_attach_tie_set_rebinds_masked_parameters_without_changing_direct_membership() -> None:
    """Nested attach should share masters while preserving direct component ownership."""
    inner_first = _component("inner-first", redshift=1.0, b_parameter=10.0)
    inner_second = _component("inner-second", redshift=1.0, b_parameter=10.0)
    direct = _component("direct", redshift=1.2, b_parameter=20.0)
    inner = _full_tie_set("inner", inner_first, inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift", "b_parameter"}), origin="user")
    outer.add_component(direct)

    outer.attach_tie_set(inner)

    assert inner.parent_tie is outer
    assert outer.member_uids == {inner.uid}
    assert inner_first.tie_set is inner
    assert inner_second.tie_set is inner
    assert direct.tie_set is outer
    assert outer.components == [direct, inner_first, inner_second]
    for name in ("redshift", "b_parameter"):
        assert inner.shared_parameters[name] is outer.shared_parameters[name]
        assert inner_first.parameters[name] is outer.shared_parameters[name]
        assert inner_second.parameters[name] is outer.shared_parameters[name]
        assert direct.parameters[name] is outer.shared_parameters[name]
    assert inner_first.parameters["column_density"] is inner.shared_parameters["column_density"]
    assert inner_first.parameters["column_density"] is not direct.parameters["column_density"]


def test_detach_tie_set_recreates_inner_masters_from_outer_values() -> None:
    """Nested detach should copy current outer state back into fresh inner masters."""
    inner_first = _component("inner-first", redshift=1.0, b_parameter=10.0)
    inner_second = _component("inner-second", redshift=1.0, b_parameter=10.0)
    direct = _component("direct", redshift=1.2, b_parameter=20.0)
    inner = _full_tie_set("inner", inner_first, inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)
    outer.set_shared_parameter("redshift", 1.5)
    outer.fix_parameter("redshift", fixed=True)
    outer.shared_parameters["redshift"].error = 0.25

    outer.detach_tie_set(inner)

    assert inner.parent_tie is None
    assert outer.member_uids == set()
    assert outer.components == [direct]
    assert inner_first.tie_set is inner
    assert inner_second.tie_set is inner
    assert inner.shared_parameters["redshift"] is not outer.shared_parameters["redshift"]
    assert inner_first.parameters["redshift"] is inner.shared_parameters["redshift"]
    assert inner_second.parameters["redshift"] is inner.shared_parameters["redshift"]
    assert inner.shared_parameters["redshift"].value == pytest.approx(1.5)
    assert inner.shared_parameters["redshift"].fixed is True
    assert inner.shared_parameters["redshift"].error == pytest.approx(0.0)


def test_inner_set_and_fix_delegate_to_parent_for_parent_mask() -> None:
    """Writes through the inner tie set should dispatch to every outer flat member."""
    inner_first = _component("inner-first", redshift=1.0)
    inner_second = _component("inner-second", redshift=1.0)
    direct = _component("direct", redshift=1.2)
    inner = _full_tie_set("inner", inner_first, inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)

    change_set = inner.set_shared_parameter("redshift", 1.4)
    fix_change_set = inner.fix_parameter("redshift", fixed=True)

    assert direct.get_parameter_value("redshift") == pytest.approx(1.4)
    assert inner_first.get_parameter_value("redshift") == pytest.approx(1.4)
    assert inner_second.get_parameter_value("redshift") == pytest.approx(1.4)
    assert direct.parameters["redshift"].fixed is True
    assert inner_first.parameters["redshift"].fixed is True
    assert {event.component_id for event in change_set.filter(ComponentChanged)} == {
        "direct",
        "inner-first",
        "inner-second",
    }
    assert {event.component_id for event in fix_change_set.filter(ComponentChanged)} == {
        "direct",
        "inner-first",
        "inner-second",
    }


def test_inner_remove_component_also_removes_it_from_parent_flat_members() -> None:
    """Removing a nested component should not leave stale outer flat membership."""
    inner_first = _component("inner-first", redshift=1.0)
    inner_second = _component("inner-second", redshift=1.0)
    direct = _component("direct", redshift=1.2)
    inner = _full_tie_set("inner", inner_first, inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)

    inner.remove_component(inner_first)

    assert inner_first.tie_set is None
    assert inner_second.tie_set is inner
    assert inner_first not in outer.components
    assert outer.components == [direct, inner_second]
    assert outer.member_uids == {inner.uid}


def test_effective_tie_set_and_participation_unit_count_cover_nested_and_direct_members() -> None:
    """Core helpers should expose parent sharing and external dissolve units."""
    inner_first = _component("inner-first", redshift=1.0)
    inner_second = _component("inner-second", redshift=1.0)
    direct = _component("direct", redshift=1.2)
    inner = _full_tie_set("inner", inner_first, inner_second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift"}), origin="user")
    outer.add_component(direct)
    outer.attach_tie_set(inner)

    assert effective_tie_set_for_parameter(inner_first, "redshift") is outer
    assert effective_tie_set_for_parameter(inner_first, "column_density") is inner
    assert effective_tie_set_for_parameter(direct, "redshift") is outer
    assert effective_tie_set_for_parameter(direct, "column_density") is None
    assert participation_unit_count(outer) == 2
    assert outer.direct_participation_count() == 1


def test_attach_rejects_partial_inner_tie_set_for_missing_parent_mask() -> None:
    """An inner tie set must already share every parameter required by the parent."""
    first = _component("first")
    second = _component("second")
    direct = _component("direct")
    inner = ParameterTieSet("inner", mask=frozenset({"redshift"}))
    inner.add_component(first)
    inner.add_component(second)
    outer = ParameterTieSet("outer", mask=frozenset({"redshift", "b_parameter"}))
    outer.add_component(direct)

    with pytest.raises(ValueError, match="does not share required parameters: b_parameter"):
        outer.attach_tie_set(inner)
