"""Mask definition utilities for wavelength exclusion."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import uuid4

from chappy.core.conversion import coerce_float

if TYPE_CHECKING:
    from collections.abc import Mapping

MaskPayloadValue = str | float | bool | None
MaskPayloadInputValue = str | float | int | bool | None

DEFAULT_MASK_COLOR = "#7f8c8d"


class MaskMode(StrEnum):
    """Representation type for a wavelength mask."""

    RANGE = "range"
    CENTER_WIDTH = "center_width"


@dataclass(slots=True)
class MaskDefinition:
    """Immutable wavelength mask definition used across core + GUI."""

    identifier: str = field(default_factory=lambda: str(uuid4()))
    label: str = ""
    mode: MaskMode = MaskMode.RANGE
    start_wavelength: float | None = None
    end_wavelength: float | None = None
    center: float | None = None
    half_width: float | None = None
    note: str = ""
    color: str | None = DEFAULT_MASK_COLOR
    enabled: bool = True
    group_id: str | None = None

    def __post_init__(self) -> None:
        """Validate the mask definition upon creation."""
        self._validate()

    @classmethod
    def from_range(
        cls,
        start_wavelength: float,
        end_wavelength: float,
        *,
        label: str | None = None,
        note: str = "",
        color: str | None = None,
        identifier: str | None = None,
    ) -> MaskDefinition:
        """Create a mask definition from explicit wavelength range."""
        start = float(start_wavelength)
        end = float(end_wavelength)
        if end < start:
            start, end = end, start
        return cls(
            identifier=identifier or str(uuid4()),
            label=label or "",
            mode=MaskMode.RANGE,
            start_wavelength=start,
            end_wavelength=end,
            center=(start + end) / 2,
            half_width=(end - start) / 2,
            note=note,
            color=color or DEFAULT_MASK_COLOR,
            enabled=True,
        )

    @property
    def wavelength_min(self) -> float:
        """Lowest wavelength covered by the mask."""
        if self.start_wavelength is None or self.end_wavelength is None:
            msg = "MaskDefinition missing range information"
            raise ValueError(msg)
        return min(self.start_wavelength, self.end_wavelength)

    @property
    def wavelength_max(self) -> float:
        """Highest wavelength covered by the mask."""
        if self.start_wavelength is None or self.end_wavelength is None:
            msg = "MaskDefinition missing range information"
            raise ValueError(msg)
        return max(self.start_wavelength, self.end_wavelength)

    @property
    def full_width(self) -> float:
        """Total wavelength span of the mask."""
        return self.wavelength_max - self.wavelength_min

    def as_tuple(self) -> tuple[float, float]:
        """Return tuple representation used by legacy APIs."""
        return (self.wavelength_min, self.wavelength_max)

    def rename(self, label: str) -> MaskDefinition:
        """Return a copy of the mask with a new label.

        Args:
            label: New label to assign to the mask.

        Returns:
            Updated mask definition.
        """
        return replace(self, label=label)

    def with_group_id(self, group_id: str | None) -> MaskDefinition:
        """Return a copy of the mask with a different group association.

        Args:
            group_id: Identifier of the group or ``None`` to clear the link.

        Returns:
            Updated mask definition.
        """
        return replace(self, group_id=group_id)

    def with_range(self, start: float, end: float) -> MaskDefinition:
        """Return a copy of the mask with an updated wavelength span.

        Args:
            start: Lower wavelength bound in Angstroms.
            end: Upper wavelength bound in Angstroms.

        Returns:
            Updated mask definition with derived center and half-width.
        """
        startf = float(start)
        endf = float(end)
        if endf < startf:
            startf, endf = endf, startf
        center = (startf + endf) / 2
        half = (endf - startf) / 2
        return replace(
            self, start_wavelength=startf, end_wavelength=endf, center=center, half_width=half
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, MaskPayloadInputValue]) -> MaskDefinition:
        """Deserialize mask definition from generic mapping."""
        identifier = str(payload.get("id", uuid4()))
        mode_raw = payload.get("mode", MaskMode.RANGE.value)
        try:
            mode = MaskMode(str(mode_raw))
        except ValueError:
            mode = MaskMode.RANGE
        return cls(
            identifier=identifier,
            label=str(payload.get("label", "")),
            mode=mode,
            start_wavelength=coerce_float(payload.get("start_wavelength"), default=None),
            end_wavelength=coerce_float(payload.get("end_wavelength"), default=None),
            center=coerce_float(payload.get("center"), default=None),
            half_width=coerce_float(payload.get("half_width"), default=None),
            note=str(payload.get("note", "")),
            color=_coerce_color(payload.get("color")),
            enabled=bool(payload.get("enabled", True)),
            group_id=_coerce_optional_str(payload.get("group_id")),
        )

    def _validate(self) -> None:
        if self.mode == MaskMode.RANGE:
            if self.start_wavelength is None or self.end_wavelength is None:
                msg = "MaskDefinition in RANGE mode requires start/end wavelengths"
                raise ValueError(msg)
        elif self.mode == MaskMode.CENTER_WIDTH:
            if self.center is None or self.half_width is None:
                msg = "MaskDefinition in CENTER_WIDTH mode requires center and half_width"
                raise ValueError(msg)
            if self.half_width <= 0:
                msg = "MaskDefinition half_width must be positive"
                raise ValueError(msg)
            if self.start_wavelength is None or self.end_wavelength is None:
                half = self.half_width
                start = self.center - half
                end = self.center + half
                object.__setattr__(self, "start_wavelength", start)
                object.__setattr__(self, "end_wavelength", end)
        if (
            self.start_wavelength is not None
            and self.end_wavelength is not None
            and self.end_wavelength < self.start_wavelength
        ):
            object.__setattr__(self, "start_wavelength", self.end_wavelength)
            object.__setattr__(self, "end_wavelength", self.start_wavelength)


def _coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_color(value: object) -> str:
    coerced = _coerce_optional_str(value)
    return coerced or DEFAULT_MASK_COLOR
