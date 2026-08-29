"""Typed input payloads for the shared spectrum plot boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AbsorptionMarkerInput:
    """Required data to render one absorption marker on the spectrum plot."""

    name: str
    rest_wavelength: float
    redshift: float
    column_density: float
    b_parameter: float
    oscillator_strength: float
    gamma: float
    component_id: str | None = None
    tie_label: str | None = None
    color: str | None = None
