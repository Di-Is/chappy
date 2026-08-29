"""Tests for absorber interaction intent coordination."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from chappy.gui.protocols.intent_types import (
    EndAbsorberDragIntent,
    ModifyAbsorberIntent,
    SelectAbsorberIntent,
    StartAbsorberDragIntent,
    UpdateAbsorberDragIntent,
)
from chappy.gui.spectrum.absorber_interaction_controller import (
    AbsorberModelMutationPort,
    AbsorberReference,
    SpectrumAbsorberInteractionController,
)
from chappy.gui.spectrum.absorber_drag_coordinator import SpectrumAbsorberDragCoordinator

if TYPE_CHECKING:
    from chappy.application.history import ComponentParameterState
    from chappy.core.components.absorber import AbsorberComponent


class _MutationOwner:
    """Record absorber model mutation requests."""

    def __init__(self) -> None:
        """Initialize the owner."""
        self.updated: list[tuple[AbsorberReference, str, float]] = []
        self.applied_drags: list[tuple[str, float, tuple[ComponentParameterState, ...]]] = []

    def update_parameter(
        self, absorber: AbsorberReference, parameter_name: str, value: float
    ) -> None:
        """Record an absorber parameter update."""
        self.updated.append((absorber, parameter_name, value))

    def apply_drag(
        self,
        component_id: str,
        new_redshift: float,
        before_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Record a completed absorber drag."""
        self.applied_drags.append((component_id, new_redshift, before_states))

    def resolve_absorber(self, absorber_id: str) -> AbsorberComponent | None:
        """Return no absorber for tests that do not inspect drag physics."""
        return None


class _DragCoordinator:
    """Record absorber drag intents."""

    def __init__(self) -> None:
        """Initialize the coordinator."""
        self.starts: list[StartAbsorberDragIntent] = []
        self.updates: list[UpdateAbsorberDragIntent] = []
        self.ends: list[EndAbsorberDragIntent] = []
        self.cancel_calls = 0

    def handle_drag_start(self, intent: StartAbsorberDragIntent) -> None:
        """Record a drag start."""
        self.starts.append(intent)

    def handle_drag_update(self, intent: UpdateAbsorberDragIntent) -> None:
        """Record a drag update."""
        self.updates.append(intent)

    def handle_drag_end(self, intent: EndAbsorberDragIntent) -> None:
        """Record a drag end."""
        self.ends.append(intent)

    def cancel_active_drags(self) -> bool:
        """Record a cancel request."""
        self.cancel_calls += 1
        return True


def _create_controller(
    *,
    mutation_owner: _MutationOwner | None = None,
    drag_coordinator: _DragCoordinator | None = None,
) -> tuple[SpectrumAbsorberInteractionController, list[str]]:
    """Create a controller with recording dependencies."""
    selections: list[str] = []
    drag_owner = drag_coordinator or _DragCoordinator()
    controller = SpectrumAbsorberInteractionController(
        mutation_provider=lambda: cast(AbsorberModelMutationPort | None, mutation_owner),
        selection_callback=selections.append,
        drag_coordinator=cast(SpectrumAbsorberDragCoordinator, drag_owner),
    )
    return controller, selections


def test_modify_absorber_intent_delegates_parameter_update() -> None:
    """Modify intents should delegate parameter mutation."""
    mutation_owner = _MutationOwner()
    controller, _selections = _create_controller(mutation_owner=mutation_owner)

    controller.coordinate_absorber_intent(
        ModifyAbsorberIntent(absorber_id="abs-1", parameter="z", value=2.2)
    )

    assert mutation_owner.updated == [("abs-1", "z", 2.2)]


def test_absorber_drag_methods_delegate_to_mutation_owner() -> None:
    """Direct drag application should delegate model mutation."""
    mutation_owner = _MutationOwner()
    controller, _selections = _create_controller(mutation_owner=mutation_owner)

    controller.apply_drag("abs-1", 2.3, ())

    assert mutation_owner.applied_drags == [("abs-1", 2.3, ())]


def test_selection_intent_ignores_missing_absorber_id() -> None:
    """Selection intents without an absorber id should be ignored."""
    controller, selections = _create_controller(mutation_owner=_MutationOwner())

    controller.coordinate_absorber_intent(SelectAbsorberIntent())

    assert selections == []


def test_drag_intents_delegate_to_drag_coordinator() -> None:
    """Drag intents should be routed to the drag coordinator."""
    drag_coordinator = _DragCoordinator()
    controller, _selections = _create_controller(
        mutation_owner=_MutationOwner(), drag_coordinator=drag_coordinator
    )
    start_intent = StartAbsorberDragIntent(
        absorber_id="abs-1", initial_wavelength=4210.0, initial_position=(4210.0, 0.8)
    )
    update_intent = UpdateAbsorberDragIntent(absorber_id="abs-1", current_wavelength=4220.0)
    end_intent = EndAbsorberDragIntent(absorber_id="abs-1", final_wavelength=4230.0)

    controller.coordinate_absorber_intent(start_intent)
    controller.coordinate_absorber_intent(update_intent)
    controller.coordinate_absorber_intent(end_intent)
    cancelled = controller.cancel_active_drags()

    assert drag_coordinator.starts == [start_intent]
    assert drag_coordinator.updates == [update_intent]
    assert drag_coordinator.ends == [end_intent]
    assert cancelled is True
    assert drag_coordinator.cancel_calls == 1
