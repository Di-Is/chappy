"""Typed context menu descriptors shared by GUI controllers."""

from __future__ import annotations

from dataclasses import dataclass

from chappy.gui.protocols.intent_types import (
    AddContinuumPointIntent,
    AddOptimizeComponentIntent,
    DeleteContinuumPointIntent,
    ToggleIdentifyPreviewLockIntent,
    ToggleOptimizeVelocityPlotIntent,
    ToggleVelocityPlotIntent,
)

type ContextMenuActionIntent = (
    AddContinuumPointIntent
    | AddOptimizeComponentIntent
    | DeleteContinuumPointIntent
    | ToggleIdentifyPreviewLockIntent
    | ToggleOptimizeVelocityPlotIntent
    | ToggleVelocityPlotIntent
)


@dataclass(frozen=True, slots=True)
class ContextMenuTriggerAction:
    """Action descriptor for a simple triggered menu action."""

    label: str
    intent: ContextMenuActionIntent | None
    enabled: bool = True
    tooltip: str | None = None


@dataclass(frozen=True, slots=True)
class ContextMenuToggleAction:
    """Action descriptor for a checkable menu action."""

    label: str
    checked: bool
    intent_when_checked: ContextMenuActionIntent
    intent_when_unchecked: ContextMenuActionIntent
    enabled: bool = True
    tooltip: str | None = None


type ContextMenuActionDescriptor = ContextMenuTriggerAction | ContextMenuToggleAction
