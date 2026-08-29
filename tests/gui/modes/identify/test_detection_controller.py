"""Tests for identify detection workflow controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from chappy.core.editing_mode import EditingMode
from chappy.core.identify_state import DetectedRegion
from chappy.gui.modes.identify.detection_controller import (
    IdentifyDetectionController,
    IdentifyDetectionPorts,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from chappy.presentation.identify import DetectionOverlayPayload


@dataclass
class _WorkflowPort:
    """Record detection workflow calls."""

    regions: list[DetectedRegion] | None
    call_count: int = 0

    def compute_detection_regions(self) -> list[DetectedRegion] | None:
        """Return configured detection regions."""
        self.call_count += 1
        return self.regions


@dataclass
class _SessionPort:
    """Record detected-region session updates."""

    cached_regions: list[DetectedRegion] = field(default_factory=list)
    set_calls: list[tuple[DetectedRegion, ...]] = field(default_factory=list)

    @property
    def detected_regions(self) -> Sequence[DetectedRegion]:
        """Return cached regions."""
        return list(self.cached_regions)

    def set_detected_regions(self, regions: Sequence[DetectedRegion]) -> None:
        """Record detected region replacement."""
        region_tuple = tuple(regions)
        self.set_calls.append(region_tuple)
        self.cached_regions = list(region_tuple)


@dataclass
class _OverlayPort:
    """Record detection overlay payloads."""

    calls: list[list[DetectionOverlayPayload]] = field(default_factory=list)

    def set_detection_regions(self, regions: list[DetectionOverlayPayload]) -> None:
        """Record detection overlay payloads."""
        self.calls.append(regions)


def _region(identifier: str = "region-1") -> DetectedRegion:
    """Build a detected region for controller tests."""
    return DetectedRegion(
        region_id=identifier,
        lambda_start=1000.0,
        lambda_end=1002.0,
        lambda_bar=1001.0,
        sigma=5.0,
        status="candidate",
    )


def _controller(
    *,
    mode: EditingMode | None = EditingMode.IDENTIFY,
    workflow_regions: list[DetectedRegion] | None,
    cached_regions: list[DetectedRegion] | None = None,
) -> tuple[IdentifyDetectionController, _WorkflowPort, _SessionPort, _OverlayPort]:
    """Create a detection controller with recording ports."""
    workflow = _WorkflowPort(workflow_regions)
    session = _SessionPort(list(cached_regions or []))
    overlay = _OverlayPort()
    controller = IdentifyDetectionController(
        IdentifyDetectionPorts(
            current_mode_provider=lambda: mode,
            workflow_provider=lambda: workflow,
            session_provider=lambda: session,
            overlay_provider=lambda: overlay,
        )
    )
    return controller, workflow, session, overlay


def test_perform_detection_updates_session() -> None:
    """Successful detection replaces session cache."""
    region = _region()
    controller, workflow, session, _overlay = _controller(workflow_regions=[region])

    result = controller.perform_detection()

    assert workflow.call_count == 1
    assert result == [region]
    assert session.set_calls == [(region,)]


def test_perform_detection_failure_reuses_cached_regions() -> None:
    """Failed detection keeps existing session cache."""
    cached = _region("cached")
    controller, _workflow, session, _overlay = _controller(
        workflow_regions=None, cached_regions=[cached]
    )

    result = controller.perform_detection()

    assert result == [cached]
    assert session.set_calls == []


def test_perform_detection_missing_workflow_fails_fast() -> None:
    """Missing detection workflow is a composition error, not cached recovery."""
    session = _SessionPort([_region("cached")])
    controller = IdentifyDetectionController(
        IdentifyDetectionPorts(
            current_mode_provider=lambda: EditingMode.IDENTIFY,
            workflow_provider=lambda: None,
            session_provider=lambda: session,
            overlay_provider=lambda: None,
        )
    )

    with pytest.raises(RuntimeError, match="detection workflow"):
        controller.perform_detection()


def test_sync_overlays_clears_when_not_identify_mode() -> None:
    """Detection overlays are cleared outside identify mode."""
    region = _region()
    controller, _workflow, _session, overlay = _controller(
        mode=EditingMode.ANALYSIS, workflow_regions=[region]
    )

    controller.sync_overlays([region])

    assert overlay.calls == [[]]


def test_sync_overlays_formats_regions_in_identify_mode() -> None:
    """Detection overlays are formatted through presentation payloads."""
    region = _region()
    controller, _workflow, _session, overlay = _controller(workflow_regions=[region])

    controller.sync_overlays([region])

    assert overlay.calls == [
        [
            {
                "id": "region-1",
                "lambda_start": 1000.0,
                "lambda_end": 1002.0,
                "status": "candidate",
                "sigma": 5.0,
                "color": "#3498db",
                "alpha": 0.22,
            }
        ]
    ]
