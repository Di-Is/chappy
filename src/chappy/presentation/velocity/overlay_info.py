"""Shared velocity overlay DTOs used across presentation and GUI layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.presentation.velocity.display_range import VelocityDisplayScopeKey
    from chappy.presentation.velocity.view_model import VelocitySliceInfo


@dataclass(slots=True)
class VelocityOverlayInfo:
    """Metadata passed when activating the shared velocity overlay."""

    selection_scope_key: str | None = None
    display_range_scope_key: VelocityDisplayScopeKey | None = None
    center_z: float | None = None
    rest_wavelength: float | None = None
    new_candidate_analysis_half_width_kms: float | None = None
    analysis_half_widths_kms: tuple[float, ...] = ()
    slices: list[VelocitySliceInfo] = field(default_factory=list)
