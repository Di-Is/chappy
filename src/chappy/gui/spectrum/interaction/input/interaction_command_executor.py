"""Execute routed spectrum interaction commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.gui.spectrum.interaction.input.routing.click_router import (
    BeginRectZoom,
    CancelMaskSelection,
    ClickCommand,
    CompleteVelocityPending,
    RouteModeClick,
    SetTargetWavelength,
    ShowContextMenu,
)
from chappy.gui.spectrum.interaction.input.routing.shortcut_router import (
    CancelRectZoom,
    EmitShortcutIntent,
    RouteModeVelocityShortcut,
    ShortcutCommand,
)
from chappy.gui.spectrum.interaction.input.routing.wheel_router import (
    EmitWheelIntent,
    WheelCommand,
)
from chappy.gui.spectrum.interaction.support.commands import CancelVelocityPending

if TYPE_CHECKING:
    from chappy.gui.protocols.intent_types import SpectrumInteractionIntent


class SpectrumInteractionCommandPort(Protocol):
    """Operations required to execute routed interaction commands."""

    def emit_interaction_intent(self, intent: SpectrumInteractionIntent) -> None:
        """Emit a typed spectrum interaction intent."""
        ...

    def cancel_rect_zoom_interaction(self, *, reason: str) -> bool:
        """Cancel the rectangle zoom interaction."""
        ...

    def resolve_velocity_toggle_wavelength(self) -> float | None:
        """Resolve the wavelength used for velocity toggle commands."""
        ...

    def enter_velocity_pending(
        self, wavelength: float | None, modifiers: int | None, *, trigger: str
    ) -> None:
        """Enter velocity pending mode."""
        ...

    def cancel_velocity_pending(self, *, reason: str) -> None:
        """Cancel velocity pending mode."""
        ...

    def emit_mode_velocity_shortcut(self) -> None:
        """Route a velocity shortcut to the active mode owner."""
        ...

    def set_target_wavelength(self, wavelength: float) -> None:
        """Update the latest target wavelength."""
        ...

    def emit_mode_click(self, position: tuple[float, float], modifiers: int) -> None:
        """Route a raw mode click to the active mode owner."""
        ...

    def cancel_mask_selection(self, *, reason: str) -> bool:
        """Cancel mask selection."""
        ...

    def complete_velocity_pending(
        self, wavelength: float, modifiers: int | None, *, trigger: str
    ) -> None:
        """Complete velocity pending mode."""
        ...

    def begin_rect_zoom_interaction(self, position: tuple[float, float], modifiers: int) -> None:
        """Begin rectangle zoom interaction."""
        ...

    def show_context_menu(self, position: tuple[float, float]) -> bool:
        """Show the spectrum context menu."""
        ...


class SpectrumInteractionCommandExecutor:
    """Execute click, shortcut, and wheel commands."""

    def __init__(self, *, port: SpectrumInteractionCommandPort) -> None:
        """Initialize the executor."""
        self._port = port

    def execute_shortcut_commands(self, commands: tuple[ShortcutCommand, ...]) -> None:
        """Execute routed keyboard shortcut commands in order."""
        for command in commands:
            if isinstance(command, EmitShortcutIntent):
                self._port.emit_interaction_intent(command.intent)
            elif isinstance(command, CancelRectZoom):
                self._port.cancel_rect_zoom_interaction(reason=command.reason)
            elif isinstance(command, CancelVelocityPending):
                self._port.cancel_velocity_pending(reason=command.reason)
            elif isinstance(command, RouteModeVelocityShortcut):
                self._port.emit_mode_velocity_shortcut()

    def execute_click_commands(self, commands: tuple[ClickCommand, ...]) -> None:
        """Execute routed click commands in order."""
        for command in commands:
            if isinstance(command, SetTargetWavelength):
                self._port.set_target_wavelength(command.wavelength)
            elif isinstance(command, RouteModeClick):
                self._port.emit_mode_click(command.position, command.modifiers)
            elif isinstance(command, CancelMaskSelection):
                self._port.cancel_mask_selection(reason=command.reason)
            elif isinstance(command, CompleteVelocityPending):
                self._port.complete_velocity_pending(
                    command.wavelength, command.modifiers, trigger=command.trigger
                )
            elif isinstance(command, CancelVelocityPending):
                self._port.cancel_velocity_pending(reason=command.reason)
            elif isinstance(command, BeginRectZoom):
                self._port.begin_rect_zoom_interaction(command.position, command.modifiers)
            elif isinstance(command, ShowContextMenu):
                self._port.show_context_menu(command.position)

    def execute_wheel_commands(self, commands: tuple[WheelCommand, ...]) -> None:
        """Execute routed wheel commands in order."""
        for command in commands:
            if isinstance(command, EmitWheelIntent):
                self._port.emit_interaction_intent(command.intent)
