"""Qt-free velocity plot presentation DTOs for identify workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class IdentifyVelocitySliceDescriptor:
    """Descriptor representing a single identify velocity subplot."""

    rest_wavelength: float
    label: str
    line_id: str | None
    is_primary: bool
    default_selected: bool
    tie_group_key: str


@dataclass(frozen=True, slots=True)
class IdentifyVelocityPlotContext:
    """Identify velocity plot context independent of concrete GUI widgets."""

    center_z: float
    rest_wavelength: float
    observed_wavelength: float
    species_label: str
    new_candidate_analysis_half_width_kms: float
    slices: tuple[IdentifyVelocitySliceDescriptor, ...]


class IdentifyVelocitySelectionPort(Protocol):
    """Selected velocity slice fields required by identify candidate creation."""

    rest_wavelength: float
    center_z: float | None
    line_id: str | None
    label: str
    is_primary: bool
    tie_group_key: str
