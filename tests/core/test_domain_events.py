"""Tests for typed core domain events."""

from __future__ import annotations

import pytest

from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.core.events import ComponentChanged, ComponentEnabledChanged


def test_component_parameter_update_returns_component_changed_event() -> None:
    """Parameter updates should return a typed component change event."""
    component = AbsorberComponent(component_id="absorber-1")

    change_set = component.set_parameter("column_density", 15.0)

    assert change_set.contains(ComponentChanged)
    assert change_set.filter(ComponentChanged)[0].component_id == "absorber-1"


def test_component_enabled_setter_dispatches_enabled_event() -> None:
    """Enabled changes should dispatch typed component events."""
    component = AbsorberComponent(component_id="absorber-1")
    dispatched = []

    component.events.subscribe(dispatched.append)
    component.enabled = False

    enabled_events = dispatched[0].filter(ComponentEnabledChanged)
    assert enabled_events[0].component_id == "absorber-1"
    assert not enabled_events[0].enabled


def test_component_set_enabled_returns_enabled_event() -> None:
    """Enabled changes should return typed component events."""
    component = AbsorberComponent(component_id="absorber-1")

    change_set = component.set_enabled(False)

    enabled_events = change_set.filter(ComponentEnabledChanged)
    assert enabled_events[0].component_id == "absorber-1"
    assert not enabled_events[0].enabled
    assert change_set.contains(ComponentChanged)


def test_multiplet_shared_parameter_returns_component_events() -> None:
    """Shared parameter changes should emit events for every member component."""
    first = AbsorberComponent(component_id="first")
    second = AbsorberComponent(component_id="second")
    tie_set = ParameterTieSet("CIV")
    tie_set.add_component(first)
    tie_set.add_component(second)

    change_set = tie_set.set_shared_parameter("redshift", 1.2)

    component_ids = {event.component_id for event in change_set.filter(ComponentChanged)}
    assert component_ids == {"first", "second"}


def test_multiplet_rejects_duplicate_component() -> None:
    """Adding the same component twice is an internal invariant violation."""
    component = AbsorberComponent(component_id="absorber-1", name="C IV 1548")
    tie_set = ParameterTieSet("CIV")
    tie_set.add_component(component)

    with pytest.raises(ValueError, match="already in tie set"):
        tie_set.add_component(component)
