"""Route mouse clicks to typed spectrum interaction commands."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt

from chappy.gui.spectrum.interaction.input.mapping.qt_input_mapper import KeyMouseIntentMapper
from chappy.gui.spectrum.interaction.support.commands import CancelVelocityPending
from chappy.presentation.interaction.interaction_contracts import InteractionChannel


@dataclass(frozen=True, slots=True)
class SetTargetWavelength:
    """Command to update the latest wavelength under the pointer."""

    wavelength: float


@dataclass(frozen=True, slots=True)
class CancelMaskSelection:
    """Command to cancel active mask selection."""

    reason: str


@dataclass(frozen=True, slots=True)
class CompleteVelocityPending:
    """Command to complete identify velocity pending mode."""

    wavelength: float
    modifiers: int
    trigger: str


@dataclass(frozen=True, slots=True)
class BeginRectZoom:
    """Command to begin a rectangle zoom interaction."""

    position: tuple[float, float]
    modifiers: int


@dataclass(frozen=True, slots=True)
class ShowContextMenu:
    """Command to show the shared spectrum context menu."""

    position: tuple[float, float]


@dataclass(frozen=True, slots=True)
class RouteModeClick:
    """Command to route a raw click to the active mode owner."""

    position: tuple[float, float]
    modifiers: int
    source: str


type ClickCommand = (
    SetTargetWavelength
    | CancelMaskSelection
    | CompleteVelocityPending
    | CancelVelocityPending
    | BeginRectZoom
    | ShowContextMenu
    | RouteModeClick
)


@dataclass(frozen=True, slots=True)
class ClickRouteState:
    """State required to route a mouse click."""

    identify_click_enabled: bool
    optimize_shift_click_enabled: bool
    active_channel: InteractionChannel | None
    velocity_pending: bool


@dataclass(frozen=True, slots=True)
class ClickRouteResult:
    """Result of routing a mouse click."""

    handled: bool
    commands: tuple[ClickCommand, ...] = ()


class SpectrumClickRouter:
    """Translate pointer clicks and interaction state to typed commands."""

    def route_click(
        self, *, position: tuple[float, float], button: str, modifiers: int, state: ClickRouteState
    ) -> ClickRouteResult:
        """Route a click to commands."""
        commands: list[ClickCommand] = [SetTargetWavelength(wavelength=float(position[0]))]

        if state.velocity_pending:
            if button == "left":
                commands.append(
                    CompleteVelocityPending(
                        wavelength=float(position[0]), modifiers=modifiers, trigger="mouse"
                    )
                )
                return ClickRouteResult(True, tuple(commands))
            if button == "right":
                commands.append(CancelVelocityPending(reason="context-menu"))
                return ClickRouteResult(True, tuple(commands))

        if button == "right" and state.active_channel is InteractionChannel.MASK_SELECTION:
            commands.append(CancelMaskSelection(reason="context-menu"))

        if button != "left":
            if button == "right":
                commands.append(ShowContextMenu(position=position))
                return ClickRouteResult(True, tuple(commands))
            return ClickRouteResult(False, tuple(commands))

        if state.active_channel is InteractionChannel.RECT_ZOOM:
            commands.append(BeginRectZoom(position=position, modifiers=modifiers))
            return ClickRouteResult(True, tuple(commands))

        shift_mask = KeyMouseIntentMapper.modifier_mask(Qt.KeyboardModifier.ShiftModifier)
        return self._route_left_click(
            position=position,
            modifiers=modifiers,
            shift_mask=shift_mask,
            state=state,
            commands=commands,
        )

    def _route_left_click(
        self,
        *,
        position: tuple[float, float],
        modifiers: int,
        shift_mask: int,
        state: ClickRouteState,
        commands: list[ClickCommand],
    ) -> ClickRouteResult:
        """Route a left click after shared preconditions have been handled."""
        if state.optimize_shift_click_enabled and (modifiers & shift_mask):
            commands.append(RouteModeClick(position=position, modifiers=modifiers, source="click"))
            return ClickRouteResult(True, tuple(commands))

        if state.identify_click_enabled:
            commands.append(RouteModeClick(position=position, modifiers=modifiers, source="click"))
            return ClickRouteResult(True, tuple(commands))

        return ClickRouteResult(False, tuple(commands))
