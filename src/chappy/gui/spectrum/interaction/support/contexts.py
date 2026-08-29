"""Shared interaction context aliases."""

from __future__ import annotations

from chappy.presentation.interaction.interaction_contracts import (
    AbsorberDragContext,
    ContinuumContext,
    MaskSelectionContext,
    RectZoomContext,
    VelocityContext,
)

type SnapshotContext = (
    RectZoomContext
    | VelocityContext
    | AbsorberDragContext
    | MaskSelectionContext
    | ContinuumContext
)
