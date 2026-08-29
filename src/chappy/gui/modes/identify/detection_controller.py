"""Identify-mode detection workflow controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.core.editing_mode import EditingMode
from chappy.presentation.identify import DetectionOverlayPayload, detection_overlay_payloads

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from chappy.core.identify_state import DetectedRegion


class IdentifyDetectionWorkflowPort(Protocol):
    """Detection computation required by identify detection routing."""

    def compute_detection_regions(self) -> list[DetectedRegion] | None:
        """Compute detected regions or return None when detection failed."""
        ...


class IdentifyDetectionSessionPort(Protocol):
    """Detected-region session state required by identify detection routing."""

    @property
    def detected_regions(self) -> Sequence[DetectedRegion]:
        """Return the currently cached detected regions."""
        ...

    def set_detected_regions(self, regions: Sequence[DetectedRegion]) -> None:
        """Replace the cached detected regions."""
        ...


class IdentifyDetectionOverlayPort(Protocol):
    """Detection overlay sink exposed by the shell spectrum surface."""

    def set_detection_regions(self, regions: list[DetectionOverlayPayload]) -> None:
        """Display detection overlay payloads."""
        ...


@dataclass(frozen=True, slots=True)
class IdentifyDetectionPorts:
    """Shell callbacks required by the identify detection controller."""

    current_mode_provider: Callable[[], EditingMode | None]
    workflow_provider: Callable[[], IdentifyDetectionWorkflowPort]
    session_provider: Callable[[], IdentifyDetectionSessionPort]
    overlay_provider: Callable[[], IdentifyDetectionOverlayPort | None]


class IdentifyDetectionController:
    """Coordinate identify detection computation, session updates, and overlays."""

    def __init__(self, ports: IdentifyDetectionPorts) -> None:
        """Initialize the controller.

        Args:
            ports: Shell callbacks for detection workflow, session, mode, and overlays.
        """
        self._ports = ports

    def perform_detection(self) -> list[DetectedRegion]:
        """Compute detections and update session state."""
        session = self._ports.session_provider()
        workflow = self._workflow()

        regions = workflow.compute_detection_regions()
        if regions is None:
            return list(session.detected_regions)

        session.set_detected_regions(regions)
        return list(regions)

    def sync_overlays(self, regions: Sequence[DetectedRegion]) -> None:
        """Synchronize detection overlays with the active mode."""
        overlay = self._ports.overlay_provider()
        if overlay is None:
            return

        if self._ports.current_mode_provider() is not EditingMode.IDENTIFY:
            overlay.set_detection_regions([])
            return

        overlay.set_detection_regions(detection_overlay_payloads(tuple(regions)))

    def clear_overlays(self) -> None:
        """Clear detection overlays from the spectrum surface."""
        overlay = self._ports.overlay_provider()
        if overlay is not None:
            overlay.set_detection_regions([])

    def _workflow(self) -> IdentifyDetectionWorkflowPort:
        """Return the required detection workflow."""
        workflow = self._ports.workflow_provider()
        if workflow is None:
            msg = "Identify detection workflow is not configured."
            raise RuntimeError(msg)
        return workflow
