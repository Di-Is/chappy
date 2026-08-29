"""Qt-independent mode shell state models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.core.editing_mode import EditingMode


@dataclass(frozen=True, slots=True)
class ModeActivationState:
    """Mode activation state exposed to shell adapters."""

    mode: EditingMode | None
    panel_active: bool


@dataclass(frozen=True, slots=True)
class ModeStatusUpdate:
    """Status update emitted by a mode controller."""

    message: str
