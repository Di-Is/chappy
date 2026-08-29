"""Translate low-level key and pointer values into interaction intents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, Qt

from chappy.gui.protocols.intent_types import PanIntent, SelectAbsorberIntent, ZoomFactorIntent

if TYPE_CHECKING:
    from collections.abc import Iterable

    from PySide6.QtGui import QKeyEvent, QMouseEvent

KeyboardIntent = ZoomFactorIntent | PanIntent | SelectAbsorberIntent
ModifierInput = Qt.KeyboardModifier | int


class KeyMouseIntentMapper:
    """Map Qt keyboard and mouse primitives to typed interaction values."""

    @staticmethod
    def modifier_mask(modifiers: ModifierInput) -> int:
        """Return an integer bit mask for Qt keyboard modifiers."""
        if isinstance(modifiers, int):
            return modifiers
        value: object = modifiers.value
        if isinstance(value, int):
            return value
        msg = f"Expected integer Qt keyboard modifier value, got {type(value).__name__}."
        raise TypeError(msg)

    @staticmethod
    def mouse_position(event: QMouseEvent) -> QPointF:
        """Return the Qt 6 floating-point local position for a mouse event."""
        return event.position()

    @staticmethod
    def key_code(event: QKeyEvent) -> int:
        """Return the integer Qt key code from a key event."""
        return int(event.key())

    def zoom_key_intent(
        self, key: int, modifiers: ModifierInput, zoom_modifiers: Iterable[Qt.KeyboardModifier]
    ) -> ZoomFactorIntent | None:
        """Return a zoom intent when a configured zoom shortcut matches."""
        if key in (int(Qt.Key.Key_Plus), int(Qt.Key.Key_Equal)):
            if self.is_any_modifier_active(modifiers, zoom_modifiers):
                return ZoomFactorIntent(factor=1.1)
            return None

        if key == int(Qt.Key.Key_Minus):
            if self.is_any_modifier_active(modifiers, zoom_modifiers):
                return ZoomFactorIntent(factor=1 / 1.1)
            return None

        return None

    @staticmethod
    def is_any_modifier_active(
        modifiers: ModifierInput, required_modifiers: Iterable[Qt.KeyboardModifier]
    ) -> bool:
        """Return True when any required keyboard modifier is active."""
        modifier_mask = KeyMouseIntentMapper.modifier_mask(modifiers)
        return any(
            bool(modifier_mask & KeyMouseIntentMapper.modifier_mask(required))
            for required in required_modifiers
        )

    @staticmethod
    def navigation_key_intent(key: int) -> KeyboardIntent | None:
        """Return an intent for mode-independent navigation keys."""
        key_to_intent: dict[int, KeyboardIntent | None] = {
            int(Qt.Key.Key_Up): ZoomFactorIntent(factor=1.1),
            int(Qt.Key.Key_Down): ZoomFactorIntent(factor=1 / 1.1),
            int(Qt.Key.Key_Left): PanIntent(fraction=-0.1),
            int(Qt.Key.Key_Right): PanIntent(fraction=0.1),
            int(Qt.Key.Key_N): SelectAbsorberIntent(direction="next"),
            int(Qt.Key.Key_P): SelectAbsorberIntent(direction="previous"),
            int(Qt.Key.Key_Tab): SelectAbsorberIntent(direction="next"),
            int(Qt.Key.Key_Backtab): SelectAbsorberIntent(direction="previous"),
            int(Qt.Key.Key_Space): None,
            int(Qt.Key.Key_Delete): None,
        }
        return key_to_intent.get(key)

    @staticmethod
    def normalize_wheel_delta(
        delta: float | QPoint | QPointF | tuple[int | float, int | float],
    ) -> tuple[float, float]:
        """Return horizontal and vertical deltas from supported wheel inputs."""
        if isinstance(delta, (QPoint, QPointF)):
            return float(delta.x()), float(delta.y())

        if isinstance(delta, tuple):
            return float(delta[0]), float(delta[1])

        return 0.0, float(delta)

    @staticmethod
    def wheel_zoom_factor(delta_y: float) -> float:
        """Convert vertical wheel delta to an exponential zoom factor."""
        if delta_y == 0:
            return 1.0

        normalized = float(delta_y) / 120.0
        if normalized == 0.0:
            normalized = 1.0 if delta_y > 0 else -1.0

        base_factor = 1.1
        return float(pow(base_factor, normalized))

    @staticmethod
    def wheel_pan_fraction(delta_x: float) -> float:
        """Convert horizontal wheel delta to a pan fraction."""
        if delta_x == 0:
            return 0.0

        normalized = float(delta_x) / 120.0
        fraction = normalized * 0.08
        if fraction > 0.5:
            return 0.5
        if fraction < -0.5:
            return -0.5
        return fraction
