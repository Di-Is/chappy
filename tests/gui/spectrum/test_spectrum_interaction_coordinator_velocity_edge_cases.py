"""Tests for SpectrumInteractionCoordinator velocity drag edge cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest
from PySide6.QtCore import Qt

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.application.spectrum.range_usecase import RangeNavigationUseCase
from chappy.gui.shell.spectrum_mode_policy import spectrum_interaction_mode_policy
from chappy.gui.spectrum.absorber_drag_coordinator import DraggingAbsorberState
from chappy.gui.spectrum.interaction_controller_factory import SpectrumInteractionControllerFactory
from chappy.gui.spectrum.navigation_controller import SpectrumNavigationControllerFactory
from chappy.gui.spectrum.spectrum_interaction_coordinator import SpectrumInteractionCoordinator
from chappy.gui.spectrum.spectrum_view_components import SpectrumViewComponents
from .fixtures.mock_spectrum_view import MockSignal, MockSpectrumDataBridge

if TYPE_CHECKING:
    from chappy.gui.spectrum.spectrum_plot import SpectrumPlotHost
    from chappy.gui.spectrum.spectrum_view import SpectrumView


class StateRecordingSpectrumView:
    """Small spectrum view fake that records public view state."""

    def __init__(self) -> None:
        """Initialize the fake view."""
        self.current_project: SpectroscopyProject | None = None
        self.cursor_history: list[Qt.CursorShape] = []
        self.data_changed = MockSignal()
        self.spectrum_plot = _RecordingPlot()
        self.plot_host = _RecordingPlotHost(self.spectrum_plot)

    def setCursor(self, cursor: Qt.CursorShape) -> None:  # noqa: N802
        """Record the cursor requested by the presenter.

        Args:
            cursor: Cursor shape applied to the view.
        """
        self.cursor_history.append(cursor)

    def get_velocity_plot_y_range(self) -> tuple[float, float] | None:
        """Return no override flux range."""
        return None


@dataclass(slots=True)
class PresenterHarness:
    """Container for a presenter and its state-recording dependencies."""

    presenter: SpectrumInteractionCoordinator
    view: StateRecordingSpectrumView


class _RecordingPlot:
    """Small plot fake that records drag cleanup calls."""

    def __init__(self) -> None:
        self.finished_absorber_ids: list[str] = []

    def finish_absorber_drag(self, absorber_id: str) -> None:
        """Record a completed/cancelled absorber drag cleanup."""
        self.finished_absorber_ids.append(absorber_id)


@dataclass(slots=True)
class _RecordingPlotHost:
    """Small plot host fake exposing the active plot widget."""

    plot_widget: _RecordingPlot


class _RangeInput:
    """Small range input fake."""

    def __init__(self) -> None:
        """Initialize the input."""
        self.wavelength_range_changed = MockSignal()


class _Interactor:
    """Small interactor fake."""

    def __init__(self) -> None:
        """Initialize the interactor."""
        self.sig_interaction_snapshot = MockSignal()
        self.sig_cursor_position_changed = MockSignal()
        self.rect_zoom_enabled = False

    def set_rect_zoom_mode(self, enabled: bool) -> None:
        """Record rectangle zoom mode."""
        self.rect_zoom_enabled = enabled

    def is_rect_zoom_mode_enabled(self) -> bool:
        """Return rectangle zoom mode."""
        return self.rect_zoom_enabled

    def set_selected_line_absorbers(self, _absorber_ids: set[str] | None) -> None:
        """Accept selected absorber updates."""


@pytest.fixture
def harness() -> PresenterHarness:
    """Create a SpectrumInteractionCoordinator with typed, state-recording collaborators."""
    view = StateRecordingSpectrumView()
    data_bridge = MockSpectrumDataBridge()
    presenter = SpectrumInteractionCoordinator(
        cast("SpectrumView", view),
        SpectrumNavigationControllerFactory(RangeNavigationUseCase()),
        SpectrumInteractionControllerFactory(),
        SpectrumViewComponents(
            data_bridge=cast("SpectrumDataBridge", data_bridge),
            plot_host=cast("SpectrumPlotHost", view.plot_host),
            range_input_controls=cast("SpectrumRangeInputControls", _RangeInput()),
            interactor=cast("SpectrumInputFacadePort", _Interactor()),
        ),
    )
    return PresenterHarness(presenter=presenter, view=view)


def start_velocity_drag(
    presenter: SpectrumInteractionCoordinator, absorber_id: str = "abs_001"
) -> None:
    """Seed an active velocity drag state.

    Args:
        presenter: Presenter under test.
        absorber_id: Component id for the seeded drag.
    """
    drag_state = DraggingAbsorberState(
        is_velocity_mode=True, rest_wavelength=1215.67, center_z=0.0, before_states=()
    )
    presenter._absorber_drag_coordinator._dragging_absorber_data[absorber_id] = drag_state


class TestVelocityDragCancellation:
    """Tests for public velocity drag cancellation."""

    def test_cancel_active_drags_clears_active_drag_and_resets_cursor(
        self, harness: PresenterHarness
    ) -> None:
        """Cancelling active drags should clear drag state and temporary plot lines."""
        start_velocity_drag(harness.presenter)
        start_velocity_drag(harness.presenter, absorber_id="abs_002")

        assert harness.presenter.cancel_active_drags()

        assert not harness.presenter._absorber_drag_coordinator.has_active_drag("abs_001")
        assert not harness.presenter._absorber_drag_coordinator.has_active_drag("abs_002")
        assert harness.view.cursor_history == [Qt.CursorShape.ArrowCursor]
        assert harness.view.spectrum_plot.finished_absorber_ids == ["abs_001", "abs_002"]

    def test_cancel_active_drags_without_active_drag_keeps_cursor_unchanged(
        self, harness: PresenterHarness
    ) -> None:
        """Cancelling an idle presenter should be a no-op."""
        assert not harness.presenter.cancel_active_drags()

        assert not harness.presenter._absorber_drag_coordinator.has_active_drag("abs_001")
        assert harness.view.cursor_history == []
        assert harness.view.spectrum_plot.finished_absorber_ids == []
