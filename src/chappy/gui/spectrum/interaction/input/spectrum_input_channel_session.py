"""Channel ownership session for spectrum input interactions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionStateSnapshot,
)

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.channels.coordinator import InteractionChannelCoordinator
    from chappy.gui.spectrum.interaction.input.spectrum_input_context import SpectrumInputContext
    from chappy.gui.spectrum.interaction.support.contexts import SnapshotContext


class SpectrumInputChannelSession:
    """Coordinate active input channel ownership and drag state."""

    def __init__(
        self, *, coordinator: InteractionChannelCoordinator, context: SpectrumInputContext
    ) -> None:
        """Initialize the channel ownership session."""
        self._coordinator = coordinator
        self._context = context

    def active_channel(self) -> InteractionChannel | None:
        """Return the currently active input channel."""
        return self._coordinator.active_channel

    def can_start(self, channel: InteractionChannel) -> bool:
        """Return whether a channel can start under current ownership."""
        return self._coordinator.can_start(channel)

    def set_active(self, channel: InteractionChannel | None) -> None:
        """Set active ownership for a channel."""
        self._coordinator.set_active(channel)

    def clear(self, channel: InteractionChannel | None = None) -> None:
        """Clear active ownership for a channel."""
        self._coordinator.clear(channel)

    def apply_snapshot(
        self, snapshot: InteractionStateSnapshot[SnapshotContext]
    ) -> InteractionChannel | None:
        """Apply a state snapshot and return the resulting active channel."""
        return self._coordinator.apply_snapshot(snapshot)

    def active_absorber_drag_id(self) -> str | None:
        """Return the active absorber drag id, if any."""
        return self._context.dragging_absorber_id

    def acquire_absorber_drag(self, absorber_id: str) -> None:
        """Acquire absorber drag ownership for an absorber."""
        self._context.dragging_absorber_id = absorber_id
        self.set_active(InteractionChannel.ABSORBER_DRAG)

    def clear_absorber_drag(self) -> None:
        """Clear absorber drag ownership and drag state."""
        self._context.dragging_absorber_id = None
        self.clear(InteractionChannel.ABSORBER_DRAG)

    def sync_absorber_drag_state(self, absorber_id: str | None) -> None:
        """Synchronize absorber drag state reported by the channel controller."""
        if absorber_id is None:
            self.clear_absorber_drag()
            return
        self.acquire_absorber_drag(absorber_id)

    def acquire_rect_zoom(self) -> None:
        """Acquire rectangle zoom ownership."""
        self.set_active(InteractionChannel.RECT_ZOOM)

    def clear_rect_zoom(self) -> None:
        """Clear rectangle zoom ownership."""
        self.clear(InteractionChannel.RECT_ZOOM)

    def acquire_mask_selection(self) -> None:
        """Acquire mask selection ownership."""
        self.set_active(InteractionChannel.MASK_SELECTION)

    def clear_mask_selection(self) -> None:
        """Clear mask selection ownership."""
        self.clear(InteractionChannel.MASK_SELECTION)
