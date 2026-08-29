"""Tests for continuum editor helper objects."""

from __future__ import annotations

from chappy.plotting.components.control_point_hit_tester import ControlPointHitTester
from chappy.plotting.components.continuum_editor import MatplotlibContinuumEditor
from chappy.presentation.interaction.interaction_contracts import (
    InteractionChannel,
    InteractionEvent,
    InteractionEventKind,
)


class _ContinuumInteractionPort:
    """Test interaction port for continuum editor routing."""

    def __init__(self, *, can_process: bool = True) -> None:
        self.can_process = can_process
        self.events: list[InteractionEvent] = []

    def can_process_continuum_event(self) -> bool:
        """Return whether continuum events can be processed."""
        return self.can_process

    def process_continuum_interaction_event(self, event: InteractionEvent) -> bool:
        """Record a continuum interaction event."""
        self.events.append(event)
        return True


def _continuum_event() -> InteractionEvent:
    """Create a minimal continuum interaction event."""
    return InteractionEvent(
        channel=InteractionChannel.CONTINUUM,
        kind=InteractionEventKind.CONTINUUM_SELECT,
        position=(4200.0, 1.0),
    )


def test_continuum_editor_requires_interaction_port() -> None:
    """Continuum events require an explicitly wired interaction port."""
    editor = MatplotlibContinuumEditor.__new__(MatplotlibContinuumEditor)
    editor._interactor = None

    try:
        editor._send_interaction_event(_continuum_event())
    except RuntimeError as exc:
        assert "continuum interaction port" in str(exc)
    else:
        raise AssertionError("Expected missing interaction port to fail fast")


def test_continuum_editor_routes_events_through_interaction_port() -> None:
    """Continuum editor should use its typed port instead of interactor internals."""
    editor = MatplotlibContinuumEditor.__new__(MatplotlibContinuumEditor)
    port = _ContinuumInteractionPort()
    editor._interactor = port

    assert editor._send_interaction_event(_continuum_event()) is True
    assert len(port.events) == 1


def test_continuum_editor_keeps_active_channel_as_recoverable_skip() -> None:
    """A competing active channel skips continuum processing without probing internals."""
    editor = MatplotlibContinuumEditor.__new__(MatplotlibContinuumEditor)
    port = _ContinuumInteractionPort(can_process=False)
    editor._interactor = port

    assert editor._send_interaction_event(_continuum_event()) is False
    assert port.events == []


def test_control_point_hit_tester_finds_nearest_display_point() -> None:
    """Hit testing should choose the nearest point within pixel tolerance."""
    tester = ControlPointHitTester()
    points = [(10.0, 1.0), (20.0, 1.0)]

    index = tester.point_index_near(
        points=points,
        target_display=(101.0, 99.0),
        data_to_display=lambda wave, flux: (wave * 10.0, flux * 100.0),
        tolerance_pixels=5.0,
    )

    assert index == 0


def test_control_point_hit_tester_detects_minimum_spacing() -> None:
    """Spacing checks should ignore the excluded index."""
    tester = ControlPointHitTester()
    points = [(10.0, 1.0), (20.0, 1.0)]

    assert tester.is_too_close_to_existing(points=points, wavelength=10.1, min_separation=0.2)
    assert not tester.is_too_close_to_existing(
        points=points, wavelength=10.1, min_separation=0.2, exclude_index=0
    )
