"""Tests for optimize parameter mutation use cases."""

from __future__ import annotations

import pytest

from chappy.application.optimize import OptimizeParameterMutationUseCase
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.base import Parameter
from chappy.core.components.tie_set import ParameterTieSet


def _component(component_id: str) -> AbsorberComponent:
    """Create a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, redshift=2.0, column_density=13.5)


def test_ensure_covering_factor_parameter_registers_core_default() -> None:
    """Covering factor initialization should not mutate the core default."""
    usecase = OptimizeParameterMutationUseCase()
    component = _component("component-1")

    parameter = usecase.ensure_covering_factor_parameter(component)

    assert parameter.name == "covering_factor"
    assert parameter.value == 1.0
    assert parameter.fixed is True
    assert usecase.is_parameter_initialized(parameter) is True

    parameter.fixed = False
    same_parameter = usecase.ensure_covering_factor_parameter(component)
    assert same_parameter is parameter
    assert same_parameter.fixed is False


def test_ensure_covering_factor_parameter_rejects_missing_core_parameter() -> None:
    """A missing covering factor is an absorber invariant violation."""
    usecase = OptimizeParameterMutationUseCase()
    component = _component("component-1")
    del component.parameters["covering_factor"]

    with pytest.raises(RuntimeError, match="missing covering_factor"):
        usecase.ensure_covering_factor_parameter(component)


def test_mark_parameter_initialized_records_external_parameter() -> None:
    """External workflows should be able to mark initialized parameters."""
    usecase = OptimizeParameterMutationUseCase()
    parameter = Parameter("covering_factor", 1.0)

    usecase.mark_parameter_initialized(parameter)

    assert usecase.is_parameter_initialized(parameter) is True


def test_parameter_value_fails_fast_for_missing_required_parameter() -> None:
    """Missing required parameters should raise a clear RuntimeError."""
    usecase = OptimizeParameterMutationUseCase()
    component = _component("component-1")
    del component.parameters["redshift"]

    with pytest.raises(RuntimeError, match="missing required parameter: redshift"):
        usecase.parameter_value(component, "redshift")


def test_apply_parameter_value_mutates_component_parameter() -> None:
    """Validated value application should mutate the component parameter."""
    usecase = OptimizeParameterMutationUseCase()
    component = _component("component-1")

    assert usecase.apply_parameter_value(component, "redshift", 2.1) is True

    assert component.parameters["redshift"].value == 2.1


def test_apply_parameter_value_skips_identical_value() -> None:
    """An identical parameter value must be reported as no change."""
    usecase = OptimizeParameterMutationUseCase()
    component = _component("component-1")

    assert usecase.apply_parameter_value(component, "redshift", 2.0) is False


def test_apply_parameter_value_rejects_missing_parameter_without_mutation() -> None:
    """Missing non-covering parameters should not create new parameters."""
    usecase = OptimizeParameterMutationUseCase()
    component = _component("component-1")

    assert usecase.apply_parameter_value(component, "velocity_offset", 10.0) is False

    assert "velocity_offset" not in component.parameters


def test_target_components_expands_shared_multiplet_values() -> None:
    """Shared multiplet values should include all grouped components."""
    usecase = OptimizeParameterMutationUseCase()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("group-1")
    tie_set.add_component(first)
    tie_set.add_component(second)

    assert usecase.target_components(first, "redshift") == (first, second)


def test_target_components_keeps_unshared_values_local() -> None:
    """Unshared parameters should only record the edited component."""
    usecase = OptimizeParameterMutationUseCase()
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("group-1")
    tie_set.add_component(first)
    tie_set.add_component(second)

    assert usecase.target_components(first, "velocity_offset") == (first,)
