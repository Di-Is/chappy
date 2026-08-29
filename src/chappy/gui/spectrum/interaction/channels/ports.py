"""Ports for channel-specific interaction controllers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chappy.presentation.interaction.interaction_contracts import (
        InteractionEvent,
        InteractionPhase,
    )


class InteractionChannelControllerPort(Protocol):
    """Common controller surface used by `SpectrumInputAdapter` for one channel."""

    @property
    def phase(self) -> InteractionPhase:
        """Return the last observed interaction phase."""
        ...

    def process_event(self, event: InteractionEvent) -> bool:
        """Process an interaction event."""
        ...

    def cancel_interaction(self, *, reason: str | None) -> bool:
        """Cancel the active interaction, if any."""
        ...


class ContinuumChannelControllerPort(InteractionChannelControllerPort, Protocol):
    """Continuum interaction controller injected by the continuum mode owner."""
