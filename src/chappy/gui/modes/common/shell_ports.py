"""Shell capability ports used by mode controllers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

from chappy.gui.modes.common.contracts import ModePanelHost, ModePanelWidget
from chappy.gui.modes.common.data_control_ports import WavelengthFieldAvailabilityPort

if TYPE_CHECKING:
    from chappy.core.editing_mode import EditingMode
    from chappy.gui.protocols.context_menu import ContextMenuActionDescriptor
    from chappy.gui.protocols.intent_types import ShowContextMenuIntent
    from chappy.presentation.velocity import VelocityOverlayInfo


class ModeLineOverlayPort(Protocol):
    """Line overlay operations available to mode lifecycle objects."""

    def show_confirmed_line_overlays(self) -> None:
        """Display confirmed line overlays for non-identify modes."""

    def show_identify_line_overlays(self) -> None:
        """Display line overlays including identify-mode temporary candidates."""

    def clear_line_overlays(self) -> None:
        """Clear line overlays for modes that do not use them."""


class ModeContinuumPort(Protocol):
    """Continuum visualization operations available to mode controllers."""

    def show_continuum(self) -> None:
        """Show continuum visualization for continuum mode."""

    def hide_continuum(self) -> None:
        """Hide continuum visualization for non-continuum modes."""


class ModeIdentifyWorkflowPort(Protocol):
    """Identify workflow operations available to identify mode."""

    def activate_identify_workflow(self) -> None:
        """Activate identify-specific workflow state."""

    def deactivate_identify_workflow(self) -> None:
        """Deactivate identify-specific workflow state."""


class ModeContextMenuProvider(Protocol):
    """Mode-local provider for spectrum context-menu actions."""

    def context_menu_actions(
        self, request: ShowContextMenuIntent
    ) -> list[ContextMenuActionDescriptor]:
        """Return context-menu actions for a mode-owned request.

        Args:
            request: Shared context-menu request.

        Returns:
            Action descriptors for the active mode.
        """


class ModeCommandSink(Protocol):
    """Mode-local sink for mode-switch and mode-owned commands."""

    def switch_mode(self, mode: EditingMode) -> None:
        """Switch the active mode.

        Args:
            mode: Target mode.
        """


class VelocityOverlayPort(Protocol):
    """Shared shell-owned velocity overlay visibility operations."""

    def show_velocity_overlay(
        self,
        overlay_info: VelocityOverlayInfo,
        *,
        context: Literal["identify", "optimize"] = "identify",
    ) -> None:
        """Show the shared velocity overlay."""

    def hide_velocity_overlay(
        self, *, context: Literal["identify", "optimize"] | None = None
    ) -> None:
        """Hide the shared velocity overlay."""

    def is_velocity_overlay_visible(self) -> bool:
        """Return whether the shared velocity overlay is visible."""


class LineOverlayRefreshPort(Protocol):
    """Shared shell-owned line overlay refresh operations."""

    def refresh_line_overlays(self) -> None:
        """Refresh displayed line overlays."""


__all__ = [
    "LineOverlayRefreshPort",
    "ModeCommandSink",
    "ModeContextMenuProvider",
    "ModeContinuumPort",
    "ModeIdentifyWorkflowPort",
    "ModeLineOverlayPort",
    "ModePanelHost",
    "ModePanelWidget",
    "VelocityOverlayPort",
    "WavelengthFieldAvailabilityPort",
]
