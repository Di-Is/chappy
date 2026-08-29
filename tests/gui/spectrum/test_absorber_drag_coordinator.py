"""Tests for the absorber drag coordinator's tie-set-aware history capture."""

from __future__ import annotations

from chappy.application.history import ComponentParameterState
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.components.tie_set import ParameterTieSet
from chappy.gui.protocols.intent_types import (
    EndAbsorberDragIntent,
    StartAbsorberDragIntent,
    UpdateAbsorberDragIntent,
)
from chappy.gui.spectrum.absorber_drag_coordinator import SpectrumAbsorberDragCoordinator


def _component(component_id: str) -> AbsorberComponent:
    """Return a deterministic absorber component."""
    return AbsorberComponent(component_id=component_id, wavelength=1215.67, redshift=2.0)


def _coordinator(
    components: dict[str, AbsorberComponent],
) -> tuple[
    SpectrumAbsorberDragCoordinator, list[tuple[str, float, tuple[ComponentParameterState, ...]]]
]:
    """Return a drag coordinator and the list its apply callback records into."""
    applied: list[tuple[str, float, tuple[ComponentParameterState, ...]]] = []

    def _apply(
        component_id: str, new_redshift: float, before_states: tuple[ComponentParameterState, ...]
    ) -> None:
        applied.append((component_id, new_redshift, before_states))

    coordinator = SpectrumAbsorberDragCoordinator(
        absorber_provider=components.get,
        velocity_overlay_provider=lambda: None,
        plot_widget_provider=lambda: None,
        drag_apply_callback=_apply,
        cursor_reset_callback=lambda: None,
    )
    return coordinator, applied


def _drag(coordinator: SpectrumAbsorberDragCoordinator, absorber_id: str) -> None:
    """Drive a full drag start/end sequence for an absorber."""
    coordinator.handle_drag_start(
        StartAbsorberDragIntent(
            absorber_id=absorber_id, initial_wavelength=1215.67, initial_position=(1215.67, 1.0)
        )
    )
    coordinator.handle_drag_end(
        EndAbsorberDragIntent(absorber_id=absorber_id, final_wavelength=1300.0)
    )


def test_drag_history_includes_tie_set_members_when_redshift_shared() -> None:
    """Dragging a component tied by redshift should capture history for all members."""
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("z-1", mask=frozenset({"redshift"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)

    coordinator, applied = _coordinator({"component-1": first, "component-2": second})
    _drag(coordinator, "component-1")

    assert len(applied) == 1
    before_states = applied[0][2]
    assert {state.component_id for state in before_states} == {first.id, second.id}


def test_drag_history_excludes_tie_set_members_without_shared_redshift() -> None:
    """Dragging a component whose tie set does not share redshift should not link members."""
    first = _component("component-1")
    second = _component("component-2")
    tie_set = ParameterTieSet("b-1", mask=frozenset({"b_parameter"}), origin="user")
    tie_set.add_component(first)
    tie_set.add_component(second)

    coordinator, applied = _coordinator({"component-1": first, "component-2": second})
    _drag(coordinator, "component-1")

    assert len(applied) == 1
    before_states = applied[0][2]
    assert {state.component_id for state in before_states} == {first.id}


def test_drag_preview_defers_scientific_apply_until_one_completion() -> None:
    """Repeated preview updates should produce exactly one completed drag command."""
    component = _component("component-1")
    coordinator, applied = _coordinator({component.id: component})
    coordinator.handle_drag_start(
        StartAbsorberDragIntent(
            absorber_id=component.id, initial_wavelength=1215.67, initial_position=(1215.67, 1.0)
        )
    )

    coordinator.handle_drag_update(
        UpdateAbsorberDragIntent(absorber_id=component.id, current_wavelength=1250.0)
    )
    coordinator.handle_drag_update(
        UpdateAbsorberDragIntent(absorber_id=component.id, current_wavelength=1275.0)
    )

    assert applied == []
    assert component.parameters["redshift"].value == 2.0

    coordinator.handle_drag_end(
        EndAbsorberDragIntent(absorber_id=component.id, final_wavelength=1300.0)
    )

    assert len(applied) == 1
    assert applied[0][0] == component.id
    assert tuple(state.component_id for state in applied[0][2]) == (component.id,)
