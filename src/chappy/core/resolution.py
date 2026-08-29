"""Resolution parameter helpers and constraints (SCR-DIA-RES support)."""

from __future__ import annotations

from dataclasses import dataclass

# Settings storage keys following docs/01_requirements/appendix/state_data_specification.md
SETTINGS_RESOLUTION_VALUE_KEY = "settings/resolution"
SETTINGS_RESOLUTION_ENABLED_KEY = "settings/resolution_enabled"


@dataclass(slots=True)
class ResolutionState:
    """Container for spectral resolution configuration."""

    value: float
    enabled: bool


# Limits sourced from docs/01_requirements/appendix/parameter_constraints.md#resolution
RESOLUTION_CONSTRAINTS = {
    "min": 10.0,
    "max": 100_000.0,
    "default": 36_000.0,
    "step": 10.0,
    "decimals": 2,
}

__all__ = [
    "RESOLUTION_CONSTRAINTS",
    "SETTINGS_RESOLUTION_ENABLED_KEY",
    "SETTINGS_RESOLUTION_VALUE_KEY",
    "ResolutionState",
]
