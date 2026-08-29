"""Adapt velocity-view drag signals to absorber drag interaction events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.core.constants import LIGHT_SPEED_KMS
from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    AbsorberDragPayload,
    Coordinate,
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.channels.ports import InteractionChannelControllerPort
    from chappy.gui.spectrum.interaction.input.ports import VelocityDragSignalPort
    from chappy.presentation.velocity import (
        VelocityDragComplete,
        VelocityDragRequest,
        VelocityDragUpdate,
    )


class VelocityDragOwnerPort(Protocol):
    """Owner operations required by `VelocityDragInteractionAdapter`."""

    def can_drag_absorber(self, absorber_id: str) -> bool:
        """Return whether an absorber can be dragged."""
        ...

    def active_absorber_drag_id(self) -> str | None:
        """Return the active absorber drag id, if any."""
        ...

    def acquire_absorber_drag(self, absorber_id: str) -> None:
        """Mark the absorber drag channel as active for the absorber."""
        ...

    def clear_absorber_drag(self) -> None:
        """Clear the active absorber drag state."""
        ...


class VelocityDragInteractionAdapter:
    """Convert velocity-view drag signals into absorber drag events."""

    def __init__(
        self,
        *,
        owner: VelocityDragOwnerPort,
        absorber_drag_controller: InteractionChannelControllerPort,
    ) -> None:
        """Initialize the adapter.

        Args:
            owner: Single owner port for channel ownership and drag identity.
            absorber_drag_controller: State controller that consumes drag events.
        """
        self._owner = owner
        self._absorber_drag_controller = absorber_drag_controller

    def set_absorber_drag_controller(self, controller: InteractionChannelControllerPort) -> None:
        """Replace the absorber drag controller dependency."""
        self._absorber_drag_controller = controller

    def connect_velocity_view(self, velocity_view: VelocityDragSignalPort) -> None:
        """Connect velocity-view drag signals."""
        velocity_view.sig_velocity_drag_requested.connect(self.on_velocity_drag_requested)
        velocity_view.sig_velocity_drag_update.connect(self.on_velocity_drag_update)
        velocity_view.sig_velocity_drag_complete.connect(self.on_velocity_drag_complete)

    def on_velocity_drag_requested(self, payload: VelocityDragRequest) -> None:
        """Handle a velocity-view drag request."""
        if not self._owner.can_drag_absorber(payload.component_id):
            return

        if self._owner.active_absorber_drag_id() is not None:
            return

        wavelength = self._observed_wavelength(
            velocity=payload.velocity,
            rest_wavelength=payload.rest_wavelength,
            center_z=payload.center_z,
        )

        self._owner.acquire_absorber_drag(payload.component_id)

        data_pos: Coordinate = (wavelength, payload.flux)
        event_payload = InteractionEvent(
            channel=InteractionChannel.ABSORBER_DRAG,
            kind=InteractionEventKind.ABSORBER_DRAG_BEGIN,
            position=data_pos,
            modifiers=0,
            payload=AbsorberDragPayload(absorber_id=payload.component_id),
        )
        handled = self._absorber_drag_controller.process_event(event_payload)
        if not handled:
            self._owner.clear_absorber_drag()
            msg = "Velocity drag begin was rejected after channel ownership was acquired."
            raise InteractionStateError(msg)

    def on_velocity_drag_update(self, payload: VelocityDragUpdate) -> None:
        """Handle a velocity-view drag update."""
        if self._owner.active_absorber_drag_id() != payload.component_id:
            return

        self._process_velocity_drag_event(
            kind=InteractionEventKind.ABSORBER_DRAG_UPDATE,
            velocity=payload.velocity,
            rest_wavelength=payload.rest_wavelength,
            flux=payload.flux,
            center_z=payload.center_z,
            failure_message="Velocity drag update was rejected during an active drag.",
        )

    def on_velocity_drag_complete(self, payload: VelocityDragComplete) -> None:
        """Handle a velocity-view drag completion."""
        if self._owner.active_absorber_drag_id() != payload.component_id:
            return

        self._process_velocity_drag_event(
            kind=InteractionEventKind.ABSORBER_DRAG_COMPLETE,
            velocity=payload.velocity,
            rest_wavelength=payload.rest_wavelength,
            flux=payload.flux,
            center_z=payload.center_z,
            failure_message="Velocity drag completion was rejected during an active drag.",
        )

    def _process_velocity_drag_event(
        self,
        *,
        kind: InteractionEventKind,
        velocity: float,
        rest_wavelength: float,
        flux: float,
        center_z: float,
        failure_message: str,
    ) -> None:
        """Convert velocity coordinates and send an absorber drag event."""
        wavelength = self._observed_wavelength(
            velocity=velocity, rest_wavelength=rest_wavelength, center_z=center_z
        )
        data_pos: Coordinate = (wavelength, flux)
        event_payload = InteractionEvent(
            channel=InteractionChannel.ABSORBER_DRAG, kind=kind, position=data_pos, modifiers=0
        )
        handled = self._absorber_drag_controller.process_event(event_payload)
        if not handled:
            raise InteractionStateError(failure_message)

    def _observed_wavelength(
        self, *, velocity: float, rest_wavelength: float, center_z: float
    ) -> float:
        """Convert velocity-space coordinates to observed wavelength."""
        return rest_wavelength * (1.0 + center_z) * (1.0 + velocity / LIGHT_SPEED_KMS)
