"""Absorber intent coordination for the shared spectrum surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.gui.protocols.intent_types import (
    EndAbsorberDragIntent,
    ModifyAbsorberIntent,
    SelectAbsorberIntent,
    StartAbsorberDragIntent,
    UpdateAbsorberDragIntent,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.application.history import ComponentParameterState
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.base import ModelComponent
    from chappy.gui.spectrum.absorber_drag_coordinator import SpectrumAbsorberDragCoordinator

type AbsorberIntent = (
    SelectAbsorberIntent
    | ModifyAbsorberIntent
    | StartAbsorberDragIntent
    | UpdateAbsorberDragIntent
    | EndAbsorberDragIntent
)
type AbsorberReference = ModelComponent | str


class AbsorberModelMutationPort(Protocol):
    """Model mutation operations required by absorber interactions."""

    def update_parameter(
        self, absorber: AbsorberReference, parameter_name: str, value: float
    ) -> None:
        """Update an absorber parameter."""
        ...

    def apply_drag(
        self,
        component_id: str,
        new_redshift: float,
        before_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Apply a completed absorber drag."""
        ...

    def resolve_absorber(self, absorber_id: str) -> AbsorberComponent | None:
        """Resolve an absorber for drag calculations."""
        ...


class SpectrumAbsorberInteractionController:
    """Dispatch absorber intents without owning model mutation."""

    def __init__(
        self,
        *,
        mutation_provider: Callable[[], AbsorberModelMutationPort | None],
        selection_callback: Callable[[str], None],
        drag_coordinator: SpectrumAbsorberDragCoordinator,
    ) -> None:
        """Initialize the absorber interaction controller."""
        self._mutation_provider = mutation_provider
        self._selection_callback = selection_callback
        self._drag_coordinator = drag_coordinator

    def coordinate_absorber_intent(self, intent: AbsorberIntent) -> None:
        """Handle absorber-related intents."""
        if isinstance(intent, SelectAbsorberIntent):
            if intent.absorber_id:
                self._selection_callback(intent.absorber_id)
            return
        if isinstance(intent, ModifyAbsorberIntent):
            self.update_parameter(intent.absorber_id, intent.parameter, intent.value)
            return
        if isinstance(intent, StartAbsorberDragIntent):
            self._drag_coordinator.handle_drag_start(intent)
            return
        if isinstance(intent, UpdateAbsorberDragIntent):
            self._drag_coordinator.handle_drag_update(intent)
            return
        if isinstance(intent, EndAbsorberDragIntent):
            self._drag_coordinator.handle_drag_end(intent)

    def update_parameter(
        self, absorber: AbsorberReference, parameter_name: str, value: float
    ) -> None:
        """Update an absorber parameter through the mutation owner."""
        self._mutation_owner().update_parameter(absorber, parameter_name, value)

    def apply_drag(
        self,
        component_id: str,
        new_redshift: float,
        before_states: tuple[ComponentParameterState, ...],
    ) -> None:
        """Apply a completed absorber drag through the mutation owner."""
        self._mutation_owner().apply_drag(component_id, new_redshift, before_states)

    def resolve_absorber(self, absorber_id: str) -> AbsorberComponent | None:
        """Resolve an absorber through the mutation owner."""
        return self._mutation_owner().resolve_absorber(absorber_id)

    def cancel_active_drags(self) -> bool:
        """Cancel all active absorber drag operations."""
        return self._drag_coordinator.cancel_active_drags()

    def _mutation_owner(self) -> AbsorberModelMutationPort:
        """Return the attached mutation owner or fail fast."""
        owner = self._mutation_provider()
        if owner is None:
            msg = "Absorber model mutation owner is required."
            raise RuntimeError(msg)
        return owner
