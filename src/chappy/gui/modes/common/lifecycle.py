"""Lifecycle contracts for mode modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chappy.core.editing_mode import EditingMode
    from chappy.core.spectroscopy_project import SpectroscopyProject


@dataclass(frozen=True, slots=True)
class ModeRefreshRequest:
    """Refresh request sent to a mode lifecycle."""

    mode: EditingMode
    reason: str


class ModeLifecycle(Protocol):
    """Lifecycle boundary implemented by mode controllers."""

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the active project.

        Args:
            project: Active project, or None when no project is open.
        """

    def activate(self) -> None:
        """Activate the mode."""

    def deactivate(self) -> None:
        """Deactivate the mode."""

    def refresh(self, request: ModeRefreshRequest) -> None:
        """Refresh mode state.

        Args:
            request: Refresh request.
        """
