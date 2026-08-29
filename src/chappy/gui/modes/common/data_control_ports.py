"""Shared data-control ports consumed across shell and mode boundaries."""

from __future__ import annotations

from typing import Protocol


class WavelengthFieldAvailabilityPort(Protocol):
    """Shared surface port controlling wavelength field availability."""

    def set_wavelength_fields_enabled(self, enabled: bool) -> None:
        """Update whether wavelength range fields are editable.

        Args:
            enabled: True when wavelength fields should be editable.
        """


__all__ = ["WavelengthFieldAvailabilityPort"]
