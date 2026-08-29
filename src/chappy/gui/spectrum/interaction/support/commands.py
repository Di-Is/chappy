"""Shared interaction commands emitted by input routers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CancelVelocityPending:
    """Command to cancel identify velocity pending mode."""

    reason: str
