"""Mutable context for spectrum input adapter state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SpectrumInputContext:
    """Store mutable input adapter state."""

    dragging_absorber_id: str | None = None
