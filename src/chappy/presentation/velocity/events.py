"""Typed payloads for velocity-view GUI events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.presentation.velocity.view_model import VelocitySliceInfo


@dataclass(frozen=True, slots=True)
class VelocityDragRequest:
    """Payload for starting absorber drag from the velocity view."""

    component_id: str
    velocity: float
    rest_wavelength: float
    flux: float
    center_z: float


@dataclass(frozen=True, slots=True)
class VelocityDragUpdate:
    """Payload for updating absorber drag from the velocity view."""

    component_id: str
    velocity: float
    rest_wavelength: float
    flux: float
    center_z: float


@dataclass(frozen=True, slots=True)
class VelocityDragComplete:
    """Payload for completing absorber drag from the velocity view."""

    component_id: str
    velocity: float
    rest_wavelength: float
    flux: float
    center_z: float


@dataclass(frozen=True, slots=True)
class VelocityContextMenuRequest:
    """Payload for context-menu requests in the velocity view."""

    velocity: float
    line_id: str
    rest_wavelength: float
    center_z: float
    global_position: tuple[int, int]


@dataclass(frozen=True, slots=True)
class VelocityComponentCreateRequest:
    """Payload for direct component creation from the velocity view."""

    velocity: float
    line_id: str
    rest_wavelength: float
    center_z: float


@dataclass(frozen=True, slots=True)
class VelocitySelectionCreateRequest:
    """Payload for creating objects from selected velocity slices."""

    selections: tuple[VelocitySliceInfo, ...]
