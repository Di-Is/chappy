"""Route wheel gestures to typed spectrum interaction commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.gui.protocols.intent_types import (
    PanIntent,
    SpectrumInteractionIntent,
    ZoomFactorIntent,
)
from chappy.gui.spectrum.interaction.input.mapping.qt_input_mapper import KeyMouseIntentMapper

if TYPE_CHECKING:
    from PySide6.QtCore import QPoint, QPointF


@dataclass(frozen=True, slots=True)
class EmitWheelIntent:
    """Command to emit a wheel-derived spectrum intent."""

    intent: SpectrumInteractionIntent


type WheelCommand = EmitWheelIntent


@dataclass(frozen=True, slots=True)
class WheelRouteResult:
    """Result of routing a wheel gesture."""

    handled: bool
    commands: tuple[WheelCommand, ...] = ()


class SpectrumWheelRouter:
    """Translate wheel gestures to typed commands."""

    def route_wheel(
        self,
        *,
        position: tuple[float, float],
        delta: float | QPoint | QPointF | tuple[int | float, int | float],
        current_range: tuple[float, float] | None,
    ) -> WheelRouteResult:
        """Route a wheel gesture to commands."""
        delta_x, delta_y = KeyMouseIntentMapper.normalize_wheel_delta(delta)
        if delta_x != 0.0 and delta_y != 0.0:
            if abs(delta_y) >= abs(delta_x):
                delta_x = 0.0
            else:
                delta_y = 0.0

        commands: list[WheelCommand] = []

        if delta_y != 0:
            factor = KeyMouseIntentMapper.wheel_zoom_factor(delta_y)
            cursor_wavelength = position[0]
            commands.append(
                EmitWheelIntent(
                    ZoomFactorIntent(
                        factor=factor,
                        center_wavelength=cursor_wavelength,
                        cursor_relative_position=self._cursor_relative_position(
                            cursor_wavelength=cursor_wavelength, current_range=current_range
                        ),
                    )
                )
            )

        if delta_x != 0:
            fraction = KeyMouseIntentMapper.wheel_pan_fraction(delta_x)
            if fraction != 0.0:
                commands.append(EmitWheelIntent(PanIntent(fraction=fraction)))

        return WheelRouteResult(bool(commands), tuple(commands))

    def _cursor_relative_position(
        self, *, cursor_wavelength: float, current_range: tuple[float, float] | None
    ) -> float | None:
        """Return cursor position within the current wavelength range."""
        if current_range is None:
            return None

        min_wave, max_wave = current_range
        range_width = max_wave - min_wave
        if range_width <= 0:
            return None
        return (cursor_wavelength - min_wave) / range_width
