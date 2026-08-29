"""Coordinate active ownership between interaction channels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionPhase,
    InteractionStateSnapshot,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.support.contexts import SnapshotContext


@dataclass
class InteractionChannelCoordinator:
    """Enforce one active interaction channel at a time."""

    _active_channel: InteractionChannel | None = None

    @property
    def active_channel(self) -> InteractionChannel | None:
        """Return the channel currently owning pointer interaction state."""
        return self._active_channel

    def can_start(self, channel: InteractionChannel) -> bool:
        """Return whether a channel can start under the current ownership."""
        return self._active_channel in (None, channel)

    def set_active(self, channel: InteractionChannel | None) -> None:
        """Set the active channel explicitly."""
        self._active_channel = channel

    def start(self, channel: InteractionChannel) -> bool:
        """Claim active ownership for a channel if allowed."""
        if not self.can_start(channel):
            return False
        self._active_channel = channel
        return True

    def clear(self, channel: InteractionChannel | None = None) -> None:
        """Clear active ownership.

        Args:
            channel: Optional channel guard. When provided, ownership is only
                cleared if the active channel matches it.
        """
        if channel is None or self._active_channel is channel:
            self._active_channel = None

    def apply_snapshot(
        self, snapshot: InteractionStateSnapshot[SnapshotContext]
    ) -> InteractionChannel | None:
        """Update active ownership from a state snapshot and return the active channel."""
        if snapshot.phase in {InteractionPhase.ARMED, InteractionPhase.ACTIVE}:
            if not self.can_start(snapshot.channel):
                msg = (
                    f"Interaction channel {snapshot.channel} cannot become active while "
                    f"{self._active_channel} is active."
                )
                raise InteractionStateError(msg)
            self._active_channel = snapshot.channel
        elif snapshot.phase in {InteractionPhase.IDLE, InteractionPhase.CANCELLED}:
            self.clear(snapshot.channel)
        return self._active_channel
