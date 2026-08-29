"""Emitter for velocity interaction snapshots."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from chappy.presentation.interaction.interaction_contracts import (
    InteractionStateSnapshot,
    VelocityContext,
)

SnapshotConsumer = Callable[[InteractionStateSnapshot[VelocityContext]], None]


class VelocitySnapshotEmitterPort(Protocol):
    """Protocol describing velocity snapshot emission behaviour."""

    def emit(self, snapshot: InteractionStateSnapshot[VelocityContext]) -> None:
        """Emit a velocity transition snapshot."""


class VelocitySnapshotEmitter:
    """Emit velocity interaction snapshots."""

    def __init__(self, *, snapshot_consumer: SnapshotConsumer) -> None:
        """Initialise the velocity snapshot emitter.

        Args:
            snapshot_consumer: Callback receiving velocity snapshots.
        """
        self._snapshot_consumer = snapshot_consumer

    def emit(self, snapshot: InteractionStateSnapshot[VelocityContext]) -> None:
        """Emit a velocity transition snapshot."""
        self._snapshot_consumer(snapshot)
