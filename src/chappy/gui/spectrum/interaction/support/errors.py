"""Interaction state transition errors."""

from __future__ import annotations


class InteractionStateError(RuntimeError):
    """Raised when an invalid interaction state transition is attempted."""
