"""Core data structures for absorption lines and regions.

These entities represent identify-mode outputs that bridge into
subsequent modelling and optimization workflows without relying on
absorber model components.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence  # noqa: TC003
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class AbsorptionLine:
    """Physical absorption line identified within a spectrum."""

    # Required fields (from AtomicLine at creation time for reproducibility)
    line_id: str
    species: str
    rest_wavelength: float
    center_z: float
    window_kms: float
    multiplet_label: str
    transition_name: str
    oscillator_strength: float
    gamma_value: float

    # Optional fields
    lambda_range: tuple[float, float] | None = None
    region_id: str | None = None
    multiplet_ids: list[str] = field(default_factory=list)
    model_ids: list[str] = field(default_factory=list)
    needs_optimization: bool = False
    created_by: str = "identify"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def observed_wavelength(self) -> float:
        """Return the observed center wavelength derived from redshift."""
        if self.rest_wavelength <= 0:
            return 0.0
        return self.rest_wavelength * (1.0 + self.center_z)


@dataclass(slots=True)
class AbsorptionRegion:
    """Logical grouping of absorption lines."""

    region_id: str
    line_ids: list[str] = field(default_factory=list)
    display_color: str = "#7f8c8d"
    analysis_range: tuple[float, float] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def attach_lines(self, lines: Iterable[str]) -> None:
        """Append lines ensuring no duplicates."""
        for line_id in lines:
            if line_id not in self.line_ids:
                self.line_ids.append(line_id)

    def remove_lines(self, lines: Sequence[str]) -> None:
        """Remove lines if present."""
        purge = set(lines)
        if not purge:
            return
        self.line_ids = [lid for lid in self.line_ids if lid not in purge]


UNASSIGNED_REGION_ID = "unassigned"

__all__ = ["UNASSIGNED_REGION_ID", "AbsorptionLine", "AbsorptionRegion"]
