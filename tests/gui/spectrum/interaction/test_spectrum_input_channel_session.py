"""Tests for spectrum input channel ownership session."""

from __future__ import annotations

from chappy.gui.spectrum.interaction.channels.coordinator import InteractionChannelCoordinator
from chappy.gui.spectrum.interaction.input.spectrum_input_channel_session import (
    SpectrumInputChannelSession,
)
from chappy.gui.spectrum.interaction.input.spectrum_input_context import SpectrumInputContext
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionId,
    InteractionPhase,
    InteractionStateSnapshot,
    RectZoomContext,
)


def test_session_acquires_and_clears_channel_ownership() -> None:
    """Session should keep local and coordinator channel state synchronized."""
    coordinator = InteractionChannelCoordinator()
    session = SpectrumInputChannelSession(coordinator=coordinator, context=SpectrumInputContext())

    session.acquire_rect_zoom()

    assert session.active_channel() is InteractionChannel.RECT_ZOOM
    assert coordinator.active_channel is InteractionChannel.RECT_ZOOM
    assert session.can_start(InteractionChannel.MASK_SELECTION) is False

    session.clear_rect_zoom()

    assert session.active_channel() is None
    assert coordinator.active_channel is None


def test_session_tracks_absorber_drag_id_with_channel() -> None:
    """Absorber drag ownership should update the mutable input context."""
    context = SpectrumInputContext()
    session = SpectrumInputChannelSession(
        coordinator=InteractionChannelCoordinator(), context=context
    )

    session.acquire_absorber_drag("abs-1")

    assert session.active_channel() is InteractionChannel.ABSORBER_DRAG
    assert session.active_absorber_drag_id() == "abs-1"
    assert context.dragging_absorber_id == "abs-1"

    session.clear_absorber_drag()

    assert session.active_channel() is None
    assert session.active_absorber_drag_id() is None
    assert context.dragging_absorber_id is None


def test_session_applies_snapshots_to_channel_state() -> None:
    """Interaction snapshots should drive active channel ownership."""
    session = SpectrumInputChannelSession(
        coordinator=InteractionChannelCoordinator(), context=SpectrumInputContext()
    )
    active_snapshot: InteractionStateSnapshot[RectZoomContext] = InteractionStateSnapshot(
        interaction_id=InteractionId("rect-1"),
        channel=InteractionChannel.RECT_ZOOM,
        phase=InteractionPhase.ACTIVE,
        context=RectZoomContext(start=(1.0, 2.0), current=(3.0, 4.0), end=None, bounds=None),
    )
    idle_snapshot: InteractionStateSnapshot[RectZoomContext] = InteractionStateSnapshot(
        interaction_id=InteractionId("rect-1"),
        channel=InteractionChannel.RECT_ZOOM,
        phase=InteractionPhase.IDLE,
        context=RectZoomContext(start=(1.0, 2.0), current=(3.0, 4.0), end=None, bounds=None),
    )

    assert session.apply_snapshot(active_snapshot) is InteractionChannel.RECT_ZOOM
    assert session.active_channel() is InteractionChannel.RECT_ZOOM

    assert session.apply_snapshot(idle_snapshot) is None
    assert session.active_channel() is None
