"""Tests for interaction channel ownership decisions."""

from __future__ import annotations

import pytest

from chappy.gui.spectrum.interaction.channels.coordinator import InteractionChannelCoordinator
from chappy.gui.spectrum.interaction.support.errors import InteractionStateError
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionId,
    InteractionPhase,
    InteractionStateSnapshot,
    RectZoomContext,
)


def test_coordinator_blocks_competing_channel_until_cleared() -> None:
    """Only the current channel should be allowed to re-enter while active."""
    coordinator = InteractionChannelCoordinator()

    assert coordinator.start(InteractionChannel.RECT_ZOOM) is True
    assert coordinator.can_start(InteractionChannel.RECT_ZOOM) is True
    assert coordinator.can_start(InteractionChannel.MASK_SELECTION) is False

    coordinator.clear(InteractionChannel.RECT_ZOOM)

    assert coordinator.active_channel is None
    assert coordinator.can_start(InteractionChannel.MASK_SELECTION) is True


def test_coordinator_tracks_snapshot_completion() -> None:
    """Snapshots should update active channel ownership."""
    coordinator = InteractionChannelCoordinator()
    active_snapshot: InteractionStateSnapshot[RectZoomContext] = InteractionStateSnapshot(
        interaction_id=InteractionId("rect-1"),
        channel=InteractionChannel.RECT_ZOOM,
        phase=InteractionPhase.ACTIVE,
        context=RectZoomContext(start=(1.0, 2.0), current=(3.0, 4.0), end=None, bounds=None),
    )
    completed_snapshot: InteractionStateSnapshot[RectZoomContext] = InteractionStateSnapshot(
        interaction_id=InteractionId("rect-1"),
        channel=InteractionChannel.RECT_ZOOM,
        phase=InteractionPhase.IDLE,
        context=RectZoomContext(start=(1.0, 2.0), current=(3.0, 4.0), end=None, bounds=None),
    )

    assert coordinator.apply_snapshot(active_snapshot) is InteractionChannel.RECT_ZOOM
    assert coordinator.apply_snapshot(completed_snapshot) is None


def test_coordinator_rejects_competing_active_snapshot() -> None:
    """Competing active snapshots indicate a broken interaction boundary."""
    coordinator = InteractionChannelCoordinator()
    coordinator.start(InteractionChannel.RECT_ZOOM)
    competing_snapshot: InteractionStateSnapshot[RectZoomContext] = InteractionStateSnapshot(
        interaction_id=InteractionId("mask-1"),
        channel=InteractionChannel.MASK_SELECTION,
        phase=InteractionPhase.ACTIVE,
        context=None,
    )

    with pytest.raises(InteractionStateError, match="cannot become active"):
        coordinator.apply_snapshot(competing_snapshot)
