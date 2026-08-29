"""Tests for spectrum project/data refresh coordination."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.spectrum.project_data_refresh_controller import (
    SpectrumProjectDataRefreshController,
)
from chappy.gui.spectrum.spectrum_data_bridge import SpectrumDataBridge


class _Signal:
    """Small signal test double."""

    def __init__(self) -> None:
        """Initialize the signal."""
        self._callbacks: list[Callable[..., None]] = []

    def connect(self, callback: Callable[..., None]) -> None:
        """Connect a callback."""
        self._callbacks.append(callback)

    def emit(self, *args: object) -> None:
        """Emit the signal to connected callbacks."""
        for callback in self._callbacks:
            callback(*args)


class _DataBridge:
    """Data bridge test double with Qt-like signals."""

    def __init__(self, project: SpectroscopyProject | None = None) -> None:
        """Initialize the bridge."""
        self.project = project
        self.project_changed = _Signal()
        self.data_updated = _Signal()
        self.range_changed = _Signal()


class _ProjectReceiver:
    """Record synchronized projects."""

    def __init__(self) -> None:
        """Initialize the receiver."""
        self.projects: list[SpectroscopyProject] = []

    def set_project(self, project: SpectroscopyProject) -> None:
        """Record project state."""
        self.projects.append(project)


class _DataRefreshReceiver:
    """Record data refreshes."""

    def __init__(self) -> None:
        """Initialize the receiver."""
        self.refresh_count = 0

    def refresh_data(self) -> None:
        """Record a data refresh."""
        self.refresh_count += 1


class _VisualUpdateReceiver:
    """Record visual updates."""

    def __init__(self) -> None:
        """Initialize the receiver."""
        self.update_count = 0

    def update(self) -> None:
        """Record a visual update."""
        self.update_count += 1


class _ProjectRefreshReceiver:
    """Record project refreshes."""

    def __init__(self) -> None:
        """Initialize the receiver."""
        self.projects: list[SpectroscopyProject] = []

    def update_from_project(self, project: SpectroscopyProject) -> None:
        """Record a project refresh."""
        self.projects.append(project)


class _ProjectLifecycleReceiver:
    """Record project attachment and initial rendering order."""

    def __init__(self, events: list[str]) -> None:
        """Store the shared event log."""
        self._events = events

    def set_project(self, _project: SpectroscopyProject) -> None:
        """Record project attachment."""
        self._events.append("set_project")

    def update_from_project(self, _project: SpectroscopyProject) -> None:
        """Record the initial project render."""
        self._events.append("update_from_project")


def test_synchronize_project_state_updates_project_receivers() -> None:
    """Project synchronization should update project-aware components."""
    project = SpectroscopyProject()
    data_bridge = _DataBridge(project)
    receiver = _ProjectReceiver()
    controller = SpectrumProjectDataRefreshController(
        data_bridge_provider=lambda: cast(SpectrumDataBridge, data_bridge),
        components_provider=lambda: (receiver, object()),
        range_changed_callback=lambda _min_wave, _max_wave, _min_flux, _max_flux: None,
        auto_scale_callback=lambda: None,
    )

    controller.synchronize_project_state()

    assert receiver.projects == [project]


def test_handle_data_updated_refreshes_matching_components() -> None:
    """Data updates should refresh components through typed runtime ports."""
    project = SpectroscopyProject()
    data_bridge = _DataBridge(project)
    data_receiver = _DataRefreshReceiver()
    visual_receiver = _VisualUpdateReceiver()
    project_receiver = _ProjectRefreshReceiver()
    controller = SpectrumProjectDataRefreshController(
        data_bridge_provider=lambda: cast(SpectrumDataBridge, data_bridge),
        components_provider=lambda: (data_receiver, visual_receiver, project_receiver),
        range_changed_callback=lambda _min_wave, _max_wave, _min_flux, _max_flux: None,
        auto_scale_callback=lambda: None,
    )

    controller.handle_data_updated()

    assert data_receiver.refresh_count == 1
    assert visual_receiver.update_count == 1
    assert project_receiver.projects == [project]


def test_handle_project_changed_renders_after_project_sync_and_auto_scale() -> None:
    """Project attachment must explicitly render without relying on model events."""
    project = SpectroscopyProject()
    data_bridge = _DataBridge(project)
    events: list[str] = []
    receiver = _ProjectLifecycleReceiver(events)
    controller = SpectrumProjectDataRefreshController(
        data_bridge_provider=lambda: cast(SpectrumDataBridge, data_bridge),
        components_provider=lambda: (receiver,),
        range_changed_callback=lambda _min_wave, _max_wave, _min_flux, _max_flux: None,
        auto_scale_callback=lambda: events.append("auto_scale"),
    )

    controller.handle_project_changed(project)

    assert events == ["set_project", "auto_scale", "update_from_project"]


def test_connected_data_bridge_signals_delegate_to_controller_callbacks() -> None:
    """Connected data bridge signals should drive project, data, and range refresh."""
    project = SpectroscopyProject()
    data_bridge = _DataBridge(project)
    project_receiver = _ProjectReceiver()
    data_receiver = _DataRefreshReceiver()
    ranges: list[tuple[float, float, float, float]] = []
    auto_scale_count = 0

    def auto_scale() -> None:
        nonlocal auto_scale_count
        auto_scale_count += 1

    controller = SpectrumProjectDataRefreshController(
        data_bridge_provider=lambda: cast(SpectrumDataBridge, data_bridge),
        components_provider=lambda: (project_receiver, data_receiver),
        range_changed_callback=lambda min_wave, max_wave, min_flux, max_flux: ranges.append(
            (min_wave, max_wave, min_flux, max_flux)
        ),
        auto_scale_callback=auto_scale,
    )

    controller.connect_data_bridge_signals(cast(SpectrumDataBridge, data_bridge))
    data_bridge.project_changed.emit(project)
    data_bridge.data_updated.emit()
    data_bridge.range_changed.emit(4100.0, 5200.0, -0.1, 1.2)

    assert project_receiver.projects == [project]
    assert data_receiver.refresh_count == 1
    assert ranges == [(4100.0, 5200.0, -0.1, 1.2)]
    assert auto_scale_count == 1
