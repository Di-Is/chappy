"""Tests for ContinuumCoordinator drag preview functionality."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import numpy as np
import pytest
from numpy.typing import NDArray
from PySide6.QtTest import QSignalSpy

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.continuum.coordinator import ContinuumCoordinator
from chappy.gui.modes.continuum.plot_adapter import ContinuumPlotAdapter, ContinuumPlotAdapterPorts
from chappy.presentation.interaction.interaction_contracts import (
    ContinuumContext,
    ContinuumOperationType,
    InteractionChannel,
    InteractionId,
    InteractionPhase,
    InteractionStateSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chappy.core.analysis import RegionAnalysisState


FloatArray = NDArray[np.float64]


@dataclass
class _CurrentContinuumProvider:
    """Return the active continuum component."""

    current: ContinuumComponent | None
    refresh_count: int = 0
    component_added: None = None

    def get_current_continuum(self) -> ContinuumComponent | None:
        """Return the configured continuum component."""
        return self.current

    def refresh_anchor_points_table(self) -> None:
        """Record a side-panel table refresh."""
        self.refresh_count += 1


@dataclass(frozen=True)
class _ObservedSpectrum:
    """Observed spectrum fake exposing wavelengths."""

    wavelength: FloatArray


@dataclass
class _ProjectModel:
    """Project model fake with observable invalidation/update state."""

    observed_spectrum: _ObservedSpectrum | None = None
    components: list[ContinuumComponent] = field(default_factory=list)
    invalidation_count: int = 0
    update_count: int = 0

    def invalidate_model(self) -> None:
        """Record model invalidation."""
        self.invalidation_count += 1

    def update_model(self) -> None:
        """Record model recalculation."""
        self.update_count += 1

    def suppress_scientific_notifications(self) -> contextlib.AbstractContextManager[None]:
        """Expose the model transaction boundary used by scientific mutations."""
        return contextlib.nullcontext()

    def snapshot_derived_state_for_transaction(self) -> tuple[int, int]:
        """Capture the focused fake's derived-state counters."""
        return self.invalidation_count, self.update_count

    def restore_derived_state_for_transaction(self, snapshot: tuple[int, int]) -> None:
        """Restore the focused fake's derived-state counters exactly."""
        self.invalidation_count, self.update_count = snapshot

    def rebuild_model_storage(self) -> None:
        """Record the canonical derived-state rebuild."""
        self.invalidate_model()
        self.update_model()

    def publish_storage_changes(self, _change_set: object) -> None:
        """Accept the isolated post-commit model notification."""


@dataclass
class _Project:
    """Project fake exposing a model."""

    model: _ProjectModel
    modified: datetime = field(default_factory=lambda: datetime.now(UTC))
    absorption_lines: dict[str, AbsorptionLine] = field(default_factory=dict)

    def region_analysis_state(self, _region_id: str) -> RegionAnalysisState | None:
        """Return no analysis state for this empty focused fake."""
        return None

    def region_analysis_states(self) -> tuple[RegionAnalysisState, ...]:
        """Return no analysis state for this empty focused fake."""
        return ()

    def set_region_analysis_state(self, _state: RegionAnalysisState) -> None:
        """Reject unexpected analysis state writes."""
        raise AssertionError("The empty project has no analysis regions.")

    def set_region_analysis_states(self, states: Iterable[RegionAnalysisState]) -> None:
        """Accept only the empty rollback snapshot."""
        assert tuple(states) == ()

    def stored_region_analysis_states_for_transaction(self) -> tuple[RegionAnalysisState, ...]:
        """Return the exact empty explicit-state storage."""
        return ()

    def replace_region_analysis_states_for_transaction(
        self, states: Iterable[RegionAnalysisState]
    ) -> None:
        """Accept only the exact empty transaction rollback state."""
        assert tuple(states) == ()

    def remove_region_analysis_state(self, _region_id: str) -> None:
        """Reject unexpected analysis state removal."""
        raise AssertionError("The empty project has no analysis regions.")

    def is_region_analysis_capable(self, _region_id: str) -> bool:
        """Return false because this focused fake has no regions."""
        return False

    def region_requires_reanalysis(self, _region_id: str) -> bool:
        """Return false because this focused fake has no regions."""
        return False

    def mark_region_needs_optimization(self, _region_id: str) -> int:
        """Reject unexpected freshness writes without regions."""
        raise AssertionError("The empty project has no analysis regions.")

    def mark_scientific_modified(self) -> None:
        """Record the accepted scientific mutation."""
        self.modified = datetime.now(UTC)


@dataclass
class _SpectrumPlot:
    """Spectrum plot fake recording continuum display operations."""

    preview_updates: list[tuple[FloatArray, FloatArray]] = field(default_factory=list)
    continuum_data_updates: list[tuple[FloatArray, FloatArray, list[tuple[float, float]]]] = field(
        default_factory=list
    )
    hide_count: int = 0
    editing_enabled: bool = False
    reference_line_count: int = 0

    def enable_continuum_editing(self, enabled: bool) -> None:
        """Record continuum editing state."""
        self.editing_enabled = enabled

    def ensure_continuum_reference_line(self) -> None:
        """Record reference line requests."""
        self.reference_line_count += 1

    def set_continuum_data(
        self,
        wavelength: FloatArray,
        continuum_flux: FloatArray,
        anchor_points: list[tuple[float, float]],
    ) -> None:
        """Record continuum display data."""
        self.continuum_data_updates.append((wavelength, continuum_flux, anchor_points))

    def hide_continuum_display(self) -> None:
        """Record continuum hide requests."""
        self.hide_count += 1

    def update_continuum_preview(self, wavelength: FloatArray, preview_flux: FloatArray) -> None:
        """Record continuum preview data."""
        self.preview_updates.append((wavelength, preview_flux))


@dataclass
class _SpectrumViewHost:
    """Spectrum view host fake returning a spectrum plot."""

    spectrum_plot: _SpectrumPlot | None

    spectrum_view: None = None

    def get_all_views(self) -> list[None]:
        """Return no view endpoints for these focused tests."""
        return []

    def get_spectrum_plot(self) -> _SpectrumPlot | None:
        """Return the configured spectrum plot."""
        return self.spectrum_plot


class _StubMainWindow:
    """Main window stub for ContinuumCoordinator tests."""

    def __init__(self) -> None:
        self.current_project: _Project | SpectroscopyProject | None = None
        self.continuum_editor: _CurrentContinuumProvider | None = None
        self.view_stack: _SpectrumViewHost | None = None
        self.mode_state_store: None = None
        self.continuum_history_recorder: _ContinuumHistory | None = None


class _ContinuumHistory:
    """Continuum history recorder for mutation-focused coordinator tests."""

    def __init__(self, *, fail_component_add: bool = False) -> None:
        """Initialize recorded operations and optional component failure."""
        self.fail_component_add = fail_component_add
        self.added_components: list[str] = []
        self.moved_points: list[tuple[list[tuple[float, float]], list[tuple[float, float]]]] = []

    @contextlib.contextmanager
    def atomic_recording(self):
        """Provide a focused history recording scope."""
        yield

    def record_cont_add_component(self, continuum: ContinuumComponent) -> None:
        """Record or reject component additions."""
        if self.fail_component_add:
            raise RuntimeError("injected coordinator component history failure")
        self.added_components.append(continuum.id)

    def record_cont_add_point(
        self,
        _continuum: ContinuumComponent,
        _before_points: list[tuple[float, float]],
        _after_points: list[tuple[float, float]],
    ) -> None:
        """Accept point additions."""

    def record_cont_delete_point(
        self,
        _continuum: ContinuumComponent,
        _before_points: list[tuple[float, float]],
        _after_points: list[tuple[float, float]],
    ) -> None:
        """Accept point deletions."""

    def record_cont_move_point(
        self,
        _continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record point movements."""
        self.moved_points.append((list(before_points), list(after_points)))

    def record_cont_reset(
        self,
        _continuum: ContinuumComponent,
        _old_points: list[tuple[float, float]],
        _new_points: list[tuple[float, float]],
    ) -> None:
        """Accept point replacements."""


@pytest.fixture
def main_window() -> _StubMainWindow:
    """Create a stub main window with required attributes."""
    main_window = _StubMainWindow()
    main_window.continuum_history_recorder = _ContinuumHistory()
    return main_window


@pytest.fixture
def coordinator(main_window: _StubMainWindow) -> ContinuumCoordinator:
    """Create a ContinuumCoordinator instance."""
    return ContinuumCoordinator(main_window)


@pytest.fixture
def continuum_component() -> ContinuumComponent:
    """Create a continuum component with sample points."""
    component = ContinuumComponent("test")
    component.continuum_points = [(4000.0, 1.0), (4500.0, 1.5), (5000.0, 1.2), (5500.0, 1.0)]
    return component


def _add_analysis_region(project: SpectroscopyProject, region_id: str) -> None:
    """Add one analysis-capable region and its fresh line."""
    line_id = f"line-{region_id}"
    project.absorption_lines[line_id] = AbsorptionLine(
        line_id=line_id,
        species="H I",
        rest_wavelength=1215.67,
        center_z=2.0,
        window_kms=100.0,
        multiplet_label="Ly alpha",
        transition_name="Ly alpha",
        oscillator_strength=0.4,
        gamma_value=1e8,
        region_id=region_id,
        needs_optimization=False,
    )
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=[line_id]
    )


def _analysis_project() -> SpectroscopyProject:
    """Create a real project with observed data and two analysis regions."""
    project = SpectroscopyProject(name="Continuum Coordinator Test")
    wavelength = np.linspace(4000.0, 5500.0, 101)
    project.model.set_observed_spectrum(
        Spectrum(wavelength=wavelength, flux=np.ones_like(wavelength))
    )
    _add_analysis_region(project, "region-1")
    _add_analysis_region(project, "region-2")
    return project


class TestComponentAdd:
    """Tests for atomic component addition through the GUI coordinator boundary."""

    def test_add_continuum_invalidates_all_regions_and_records_history(
        self, coordinator: ContinuumCoordinator, main_window: _StubMainWindow
    ) -> None:
        """A coordinator add commits one component, all freshness, and one command."""
        project = _analysis_project()
        main_window.current_project = project
        history = main_window.continuum_history_recorder
        assert history is not None
        status_spy = QSignalSpy(coordinator.status_message)

        coordinator.add_continuum()

        continua = [
            component
            for component in project.model.components
            if isinstance(component, ContinuumComponent)
        ]
        assert len(continua) == 1
        assert history.added_components == [continua[0].id]
        assert status_spy.count() == 1
        assert all(
            state.current_revision == AnalysisRevision(1)
            for state in project.region_analysis_states()
        )
        assert all(line.needs_optimization for line in project.absorption_lines.values())

    def test_add_continuum_history_failure_leaves_no_component(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A rejected history command rolls back component and global freshness."""
        project = _analysis_project()
        modified_before = project.modified
        main_window.current_project = project
        main_window.continuum_history_recorder = _ContinuumHistory(fail_component_add=True)
        warnings: list[str] = []
        monkeypatch.setattr(
            "chappy.gui.modes.continuum.coordinator.QMessageBox.warning",
            lambda _parent, _title, message: warnings.append(message),
        )

        coordinator.add_continuum()

        assert not any(
            isinstance(component, ContinuumComponent) for component in project.model.components
        )
        assert warnings == [
            "Could not add continuum:\ninjected coordinator component history failure"
        ]
        assert all(
            state.current_revision == AnalysisRevision(0)
            for state in project.region_analysis_states()
        )
        assert all(not line.needs_optimization for line in project.absorption_lines.values())
        assert project.modified == modified_before


class TestActivePhasePreview:
    """Tests for ACTIVE phase preview during drag operations."""

    def test_active_phase_move_calls_preview_update(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """ACTIVE + MOVE snapshot should trigger preview update."""
        wavelength = np.linspace(4000.0, 5500.0, 100)
        main_window.continuum_editor = _CurrentContinuumProvider(continuum_component)
        main_window.current_project = _Project(
            _ProjectModel(observed_spectrum=_ObservedSpectrum(wavelength=wavelength))
        )
        spectrum_plot = _SpectrumPlot()
        main_window.view_stack = _SpectrumViewHost(spectrum_plot)

        # Create ACTIVE phase snapshot
        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-move-1"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ACTIVE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 1.8),
                end_position=None,
                validation_result=None,
                cancel_reason=None,
            ),
        )

        coordinator._on_continuum_snapshot(snapshot)

        assert len(spectrum_plot.preview_updates) == 1
        updated_wavelength, updated_flux = spectrum_plot.preview_updates[0]
        np.testing.assert_array_equal(updated_wavelength, wavelength)
        expected_points = continuum_component.get_continuum_points()
        expected_points[1] = (4600.0, 1.8)
        np.testing.assert_allclose(
            updated_flux, ContinuumComponent.calculate_from_points(expected_points, wavelength)
        )

    def test_active_phase_move_does_not_modify_model(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """ACTIVE + MOVE should NOT modify the continuum model."""
        project_model = _ProjectModel()
        main_window.continuum_editor = _CurrentContinuumProvider(continuum_component)
        main_window.current_project = _Project(project_model)
        main_window.view_stack = _SpectrumViewHost(_SpectrumPlot())

        original_points = continuum_component.get_continuum_points()

        # Create ACTIVE phase snapshot
        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-move-1"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ACTIVE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 1.8),
                end_position=None,
                validation_result=None,
                cancel_reason=None,
            ),
        )

        # Mock view_stack to prevent actual preview rendering
        main_window.view_stack = None

        coordinator._on_continuum_snapshot(snapshot)

        assert project_model.invalidation_count == 0
        assert project_model.update_count == 0

        # Verify continuum points are unchanged
        assert continuum_component.get_continuum_points() == original_points

    def test_active_phase_move_requires_view_stack(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """ACTIVE + MOVE preview requires the configured view stack."""
        wavelength = np.linspace(4000.0, 5500.0, 100)
        main_window.continuum_editor = _CurrentContinuumProvider(continuum_component)
        main_window.current_project = _Project(
            _ProjectModel(observed_spectrum=_ObservedSpectrum(wavelength=wavelength))
        )
        main_window.view_stack = None

        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-move-1"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ACTIVE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 1.8),
                end_position=None,
                validation_result=None,
                cancel_reason=None,
            ),
        )

        with pytest.raises(RuntimeError, match="requires a view stack"):
            coordinator._on_continuum_snapshot(snapshot)

    def test_active_phase_move_requires_spectrum_plot(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """ACTIVE + MOVE preview requires the configured spectrum plot."""
        wavelength = np.linspace(4000.0, 5500.0, 100)
        main_window.continuum_editor = _CurrentContinuumProvider(continuum_component)
        main_window.current_project = _Project(
            _ProjectModel(observed_spectrum=_ObservedSpectrum(wavelength=wavelength))
        )
        main_window.view_stack = _SpectrumViewHost(None)

        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-move-1"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ACTIVE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 1.8),
                end_position=None,
                validation_result=None,
                cancel_reason=None,
            ),
        )

        with pytest.raises(RuntimeError, match="requires a spectrum plot"):
            coordinator._on_continuum_snapshot(snapshot)


class TestIdlePhaseCommit:
    """Tests for IDLE phase that commits changes to model."""

    def test_idle_phase_move_commits_change(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """IDLE + MOVE should commit the change to the model."""
        project_model = _ProjectModel()
        main_window.continuum_editor = _CurrentContinuumProvider(continuum_component)
        main_window.current_project = _Project(project_model)
        main_window.view_stack = _SpectrumViewHost(_SpectrumPlot())

        # Create IDLE phase snapshot
        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-move-1"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.IDLE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 1.8),
                end_position=(4600.0, 1.8),
                validation_result=None,
                cancel_reason=None,
            ),
        )

        coordinator._on_continuum_snapshot(snapshot)

        assert project_model.invalidation_count == 1
        assert project_model.update_count == 1

        # Verify continuum point was moved
        points = continuum_component.get_continuum_points()
        # Point should have been moved (note: it gets sorted by wavelength)
        assert any(abs(p[0] - 4600.0) < 1.0 and abs(p[1] - 1.8) < 0.01 for p in points)

    def test_idle_move_invalidates_every_nonempty_analysis_region(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """Interactive movement is a global scientific mutation across real regions."""
        project = _analysis_project()
        project.model.add_component(continuum_component)
        provider = _CurrentContinuumProvider(continuum_component)
        main_window.current_project = project
        main_window.continuum_editor = provider
        main_window.view_stack = _SpectrumViewHost(_SpectrumPlot())
        history = main_window.continuum_history_recorder
        assert history is not None
        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-move-all-regions"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.IDLE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 1.8),
                end_position=(4600.0, 1.8),
                validation_result=None,
                cancel_reason=None,
            ),
        )

        coordinator._on_continuum_snapshot(snapshot)

        assert history.moved_points == [
            (
                [(4000.0, 1.0), (4500.0, 1.5), (5000.0, 1.2), (5500.0, 1.0)],
                [(4000.0, 1.0), (4600.0, 1.8), (5000.0, 1.2), (5500.0, 1.0)],
            )
        ]
        assert provider.refresh_count == 1
        assert all(
            state.current_revision == AnalysisRevision(1)
            for state in project.region_analysis_states()
        )
        assert all(line.needs_optimization for line in project.absorption_lines.values())

    def test_idle_move_to_same_position_is_no_change(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """An identical interactive result emits no history, stale state, or refresh."""
        project = _analysis_project()
        project.model.add_component(continuum_component)
        provider = _CurrentContinuumProvider(continuum_component)
        main_window.current_project = project
        main_window.continuum_editor = provider
        main_window.view_stack = _SpectrumViewHost(_SpectrumPlot())
        history = main_window.continuum_history_recorder
        assert history is not None
        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-move-no-change"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.IDLE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4500.0, 1.5),
                end_position=(4500.0, 1.5),
                validation_result=None,
                cancel_reason=None,
            ),
        )

        coordinator._on_continuum_snapshot(snapshot)

        assert history.moved_points == []
        assert provider.refresh_count == 0
        assert all(
            state.current_revision == AnalysisRevision(0)
            for state in project.region_analysis_states()
        )
        assert all(not line.needs_optimization for line in project.absorption_lines.values())


class TestPreviewCalculation:
    """Tests for preview curve calculation."""

    def test_update_continuum_preview_calculates_curve(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """Preview update should calculate curve with modified point."""
        wavelength = np.linspace(4000, 5500, 100)
        main_window.current_project = _Project(
            _ProjectModel(observed_spectrum=_ObservedSpectrum(wavelength=wavelength))
        )
        spectrum_plot = _SpectrumPlot()
        main_window.view_stack = _SpectrumViewHost(spectrum_plot)
        main_window.continuum_editor = _CurrentContinuumProvider(continuum_component)

        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-preview-1"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ACTIVE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 2.0),
                end_position=None,
                validation_result=None,
                cancel_reason=None,
            ),
        )
        coordinator._on_continuum_snapshot(snapshot)

        assert len(spectrum_plot.preview_updates) == 1
        updated_wavelength, updated_flux = spectrum_plot.preview_updates[0]
        np.testing.assert_array_equal(updated_wavelength, wavelength)
        assert len(updated_flux) == len(wavelength)

    def test_preview_does_not_modify_original_points(
        self,
        coordinator: ContinuumCoordinator,
        main_window: _StubMainWindow,
        continuum_component: ContinuumComponent,
    ) -> None:
        """Preview calculation should not modify the original continuum points."""
        wavelength = np.linspace(4000, 5500, 100)
        main_window.current_project = _Project(
            _ProjectModel(observed_spectrum=_ObservedSpectrum(wavelength=wavelength))
        )
        main_window.view_stack = _SpectrumViewHost(_SpectrumPlot())
        main_window.continuum_editor = _CurrentContinuumProvider(continuum_component)

        # Record original points
        original_points = continuum_component.get_continuum_points()

        snapshot = InteractionStateSnapshot(
            interaction_id=InteractionId("continuum-preview-1"),
            channel=InteractionChannel.CONTINUUM,
            phase=InteractionPhase.ACTIVE,
            context=ContinuumContext(
                operation_type=ContinuumOperationType.MOVE,
                point_index=1,
                start_position=(4500.0, 1.5),
                current_position=(4600.0, 2.0),
                end_position=None,
                validation_result=None,
                cancel_reason=None,
            ),
        )
        coordinator._on_continuum_snapshot(snapshot)

        # Original points should be unchanged
        assert continuum_component.get_continuum_points() == original_points


class TestContinuumPlotAdapterBoundary:
    """Tests for continuum plot adapter required collaborator boundaries."""

    def test_apply_mode_visualization_without_project_keeps_required_plot_boundary(self) -> None:
        """No project is recoverable only after required plot collaborators exist."""
        spectrum_plot = _SpectrumPlot()
        adapter = ContinuumPlotAdapter(
            ContinuumPlotAdapterPorts(
                project_provider=lambda: None,
                view_stack_provider=lambda: _SpectrumViewHost(spectrum_plot),
                table_refresh_callback=lambda: None,
            )
        )

        adapter.apply_mode_visualization(EditingMode.CONTINUUM)

        assert spectrum_plot.editing_enabled is False
        assert spectrum_plot.reference_line_count == 0

    def test_apply_mode_visualization_requires_view_stack(self) -> None:
        """Missing view stack is a composition error."""
        adapter = ContinuumPlotAdapter(
            ContinuumPlotAdapterPorts(
                project_provider=lambda: None,
                view_stack_provider=lambda: None,
                table_refresh_callback=lambda: None,
            )
        )

        with pytest.raises(RuntimeError, match="requires a view stack"):
            adapter.apply_mode_visualization(EditingMode.CONTINUUM)
