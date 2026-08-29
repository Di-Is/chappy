"""Qt-free presentation helpers for identify detection overlays."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, TypedDict

if TYPE_CHECKING:
    from chappy.core.identify_state import RegionStatus


class DetectionOverlayPayload(TypedDict):
    """Typed payload describing one detection overlay region."""

    id: str
    lambda_start: float
    lambda_end: float
    status: str
    sigma: float
    color: str
    alpha: float


type DetectionStatusPalette = Mapping[str, tuple[str, float]]

DEFAULT_DETECTION_STATUS_PALETTE: DetectionStatusPalette = {
    "identified": ("#2ecc71", 0.24),
    "candidate": ("#3498db", 0.22),
    "unused": ("#95a5a6", 0.18),
}


class DetectedRegionPort(Protocol):
    """Detected region fields required by identify detection overlays."""

    @property
    def region_id(self) -> str:
        """Return the detected region identifier."""
        ...

    @property
    def lambda_start(self) -> float:
        """Return the lower wavelength bound."""
        ...

    @property
    def lambda_end(self) -> float:
        """Return the upper wavelength bound."""
        ...

    @property
    def sigma(self) -> float:
        """Return detection significance."""
        ...

    @property
    def status(self) -> RegionStatus:
        """Return detection status."""
        ...


def detection_overlay_payload(
    region: DetectedRegionPort, palette: DetectionStatusPalette = DEFAULT_DETECTION_STATUS_PALETTE
) -> DetectionOverlayPayload:
    """Build a spectrum overlay payload for a detected region.

    Args:
        region: Detected region boundary.
        palette: Mapping from status to display color and alpha.

    Returns:
        Spectrum detection overlay payload.
    """
    color, alpha = palette.get(region.status, ("#95a5a6", 0.12))
    return {
        "id": region.region_id,
        "lambda_start": float(region.lambda_start),
        "lambda_end": float(region.lambda_end),
        "status": region.status,
        "sigma": float(region.sigma),
        "color": color,
        "alpha": alpha,
    }


def detection_overlay_payloads(
    regions: tuple[DetectedRegionPort, ...],
    palette: DetectionStatusPalette = DEFAULT_DETECTION_STATUS_PALETTE,
) -> list[DetectionOverlayPayload]:
    """Build spectrum overlay payloads for detected regions.

    Args:
        regions: Detected region boundaries.
        palette: Mapping from status to display color and alpha.

    Returns:
        Spectrum detection overlay payloads.
    """
    return [detection_overlay_payload(region, palette) for region in regions]
