"""Continuum editor behaviour tests."""

from __future__ import annotations

import contextlib
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import numpy.typing as npt
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

from chappy.core.components.continuum import ContinuumComponent
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.core.spectrum import Spectrum
from chappy.gui.modes.mode_state_store import ModeStateStore
from chappy.gui.modes.continuum.editor import ContinuumEditor
from scripts.i18n_lupdate import run_lupdate


def _build_project_with_continuum() -> tuple[SpectroscopyProject, ContinuumComponent]:
    project = SpectroscopyProject()
    wavelengths = cast("npt.NDArray[np.float64]", np.linspace(4000.0, 4100.0, 5))
    flux: npt.NDArray[np.float64] = np.ones_like(wavelengths)
    spectrum = Spectrum(wavelength=wavelengths, flux=flux)
    project.model.set_observed_spectrum(spectrum)

    continuum = ContinuumComponent("Continuum")
    continuum.continuum_points = [
        (float(wavelengths[0]), 1.0),
        (float(wavelengths[len(wavelengths) // 2]), 1.0),
        (float(wavelengths[-1]), 1.0),
    ]

    project.model.add_component(continuum)
    return project, continuum


def _build_project_without_continuum() -> SpectroscopyProject:
    """Create a project with observed data and no continuum component."""
    project = SpectroscopyProject()
    wavelengths = cast("npt.NDArray[np.float64]", np.linspace(4000.0, 4200.0, 201))
    flux: npt.NDArray[np.float64] = np.linspace(0.8, 1.2, len(wavelengths))
    project.model.set_observed_spectrum(Spectrum(wavelength=wavelengths, flux=flux))
    return project


def _add_analysis_region(project: SpectroscopyProject, region_id: str) -> None:
    """Add one analysis-capable region with a fresh line flag."""
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


class _ContinuumHistory:
    """Continuum history fake with optional record failure injection."""

    def __init__(self, *, fail_add: bool = False, fail_component_add: bool = False) -> None:
        """Initialize history recording state."""
        self.fail_add = fail_add
        self.fail_component_add = fail_component_add
        self.added: list[tuple[list[tuple[float, float]], list[tuple[float, float]]]] = []
        self.added_components: list[str] = []
        self.deleted: list[tuple[list[tuple[float, float]], list[tuple[float, float]]]] = []
        self.moved: list[tuple[list[tuple[float, float]], list[tuple[float, float]]]] = []
        self.resets: list[tuple[list[tuple[float, float]], list[tuple[float, float]]]] = []

    @contextlib.contextmanager
    def atomic_recording(self):
        """Provide a focused history transaction scope."""
        yield

    def record_cont_add_point(
        self,
        _continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record or reject a continuum point addition."""
        if self.fail_add:
            raise RuntimeError("injected continuum history failure")
        self.added.append((list(before_points), list(after_points)))

    def record_cont_add_component(self, continuum: ContinuumComponent) -> None:
        """Record or reject a continuum component addition."""
        if self.fail_component_add:
            raise RuntimeError("injected continuum component history failure")
        self.added_components.append(continuum.id)

    def record_cont_delete_point(
        self,
        _continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record one continuum point deletion."""
        self.deleted.append((list(before_points), list(after_points)))

    def record_cont_move_point(
        self,
        _continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record one continuum point move."""
        self.moved.append((list(before_points), list(after_points)))

    def record_cont_reset(
        self,
        _continuum: ContinuumComponent,
        _old_points: list[tuple[float, float]],
        _new_points: list[tuple[float, float]],
    ) -> None:
        """Record one complete point replacement."""
        self.resets.append((list(_old_points), list(_new_points)))


def test_clear_points_preserves_defaults(qtbot: "QtBot") -> None:
    project, continuum = _build_project_with_continuum()

    mode_state_store = ModeStateStore(project=project)
    mode_state_store.switch_mode(EditingMode.CONTINUUM)

    editor = ContinuumEditor(project=project, mode_state_store=mode_state_store)
    editor.set_project(project)
    editor.set_history_recorder(_ContinuumHistory())
    qtbot.addWidget(editor)

    assert editor.current_continuum is continuum

    continuum.add_continuum_point(4030.0, 0.9)
    editor._update_anchor_points_table()

    assert continuum.num_continuum_points() == 4

    observed = project.model.observed_spectrum
    assert observed is not None

    expected_points = [
        (float(observed.wavelength[0]), 1.0),
        (float(observed.wavelength[len(observed.wavelength) // 2]), 1.0),
        (float(observed.wavelength[-1]), 1.0),
    ]

    clear_all_button = editor.clear_all_btn
    assert clear_all_button is not None

    with qtbot.waitSignal(editor.continuum_updated, timeout=1000):
        QTest.mouseClick(clear_all_button, Qt.MouseButton.LeftButton)

    remaining_points = continuum.get_continuum_points()

    assert remaining_points == expected_points
    assert continuum.num_continuum_points() == 3


def test_continuum_point_add_invalidates_every_analysis_region(qtbot: "QtBot") -> None:
    """A continuum point edit must stale every analysis-capable region."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    _add_analysis_region(project, "region-2")
    history = _ContinuumHistory()
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(history)
    qtbot.addWidget(editor)

    editor.request_add_point(4075.0, 0.9)

    assert (4075.0, 0.9) in continuum.continuum_points
    assert history.added == [
        (
            [(4000.0, 1.0), (4050.0, 1.0), (4100.0, 1.0)],
            [(4000.0, 1.0), (4050.0, 1.0), (4075.0, 0.9), (4100.0, 1.0)],
        )
    ]
    assert all(
        state.current_revision == AnalysisRevision(1) for state in project.region_analysis_states()
    )
    assert all(line.needs_optimization for line in project.absorption_lines.values())


def test_continuum_history_failure_rolls_back_points_and_freshness(qtbot: "QtBot") -> None:
    """A failed history record must restore continuum, revisions, and line flags."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    history = _ContinuumHistory(fail_add=True)
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(history)
    qtbot.addWidget(editor)
    points_before = continuum.get_continuum_points()
    modified_before = project.modified

    editor.request_add_point(4075.0, 0.9)

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert continuum.continuum_points == points_before
    assert state.current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert project.modified == modified_before


def test_continuum_refresh_failure_keeps_committed_scientific_state(
    qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-commit UI refresh failure must not revert continuum or freshness."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(_ContinuumHistory())
    qtbot.addWidget(editor)

    def _fail_refresh() -> None:
        raise RuntimeError("injected continuum refresh failure")

    monkeypatch.setattr(editor, "_update_anchor_points_table", _fail_refresh)

    editor.request_add_point(4075.0, 0.9)

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert (4075.0, 0.9) in continuum.continuum_points
    assert state.current_revision == AnalysisRevision(1)
    assert project.absorption_lines["line-region-1"].needs_optimization is True


@pytest.mark.parametrize(
    "entry",
    (
        "add_component",
        "table_edit",
        "table_delete",
        "context_add",
        "reset_points",
        "auto_estimate_existing",
        "auto_estimate_create",
    ),
)
def test_direct_entry_refresh_failure_keeps_commit_and_runs_later_observers(
    entry: str, qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every direct editor entry isolates refresh failure after its scientific commit."""
    if entry in {"add_component", "auto_estimate_create"}:
        project = _build_project_without_continuum()
        continuum = None
    else:
        project, continuum = _build_project_with_continuum()
        if entry in {"table_delete", "reset_points"}:
            continuum.continuum_points.append((4075.0, 0.9))
            continuum.continuum_points.sort(key=lambda point: point[0])

    _add_analysis_region(project, "region-1")
    history = _ContinuumHistory()
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(history)
    qtbot.addWidget(editor)

    component_notifications: list[ContinuumComponent] = []
    update_notifications: list[ContinuumComponent] = []
    plot_refreshes: list[None] = []
    status_messages: list[str] = []
    editor.component_added.connect(component_notifications.append)
    editor.continuum_updated.connect(update_notifications.append)
    editor.status_message.connect(status_messages.append)
    monkeypatch.setattr(editor, "_refresh_plot_display", lambda: plot_refreshes.append(None))

    def fail_table_refresh() -> None:
        raise RuntimeError("injected direct-entry table observer failure")

    monkeypatch.setattr(editor, "_update_anchor_points_table", fail_table_refresh)

    if entry == "add_component":
        editor.add_continuum()
    elif entry == "table_edit":
        table = editor.anchor_points_table
        assert table is not None
        item = table.item(0, editor.COLUMN_FLUX)
        assert item is not None
        item.setText("0.8000")
    elif entry == "table_delete":
        editor._on_table_delete_clicked(3)
    elif entry == "context_add":
        editor.request_add_point(4075.0, 0.9)
    elif entry == "reset_points":
        assert editor._reset_continuum_points() is True
    elif entry in {"auto_estimate_existing", "auto_estimate_create"}:
        editor._run_auto_estimate()
    else:
        raise AssertionError(f"Unhandled test entry: {entry}")

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert state.current_revision == AnalysisRevision(1)
    assert project.absorption_lines["line-region-1"].needs_optimization is True
    assert not any(
        "error" in message.lower() or "failed" in message.lower() for message in status_messages
    )

    committed_continuum = editor.current_continuum
    assert committed_continuum is not None
    if entry == "add_component":
        assert history.added_components == [committed_continuum.id]
        assert component_notifications == [committed_continuum]
        assert update_notifications == []
        assert plot_refreshes == []
    elif entry == "table_edit":
        assert committed_continuum.continuum_points[0][1] == 0.8
        assert len(history.moved) == 1
    elif entry == "table_delete":
        assert committed_continuum.num_continuum_points() == 3
        assert len(history.deleted) == 1
    elif entry == "context_add":
        assert (4075.0, 0.9) in committed_continuum.continuum_points
        assert len(history.added) == 1
    elif entry == "reset_points":
        assert (4075.0, 0.9) not in committed_continuum.continuum_points
        assert len(history.resets) == 1
    elif entry == "auto_estimate_existing":
        assert len(history.resets) == 1
        assert status_messages == ["Continuum auto estimate complete"]
    elif entry == "auto_estimate_create":
        assert history.added_components == [committed_continuum.id]
        assert component_notifications == [committed_continuum]
        assert status_messages == ["Continuum auto estimate complete"]

    if entry not in {"add_component"}:
        assert update_notifications == [committed_continuum]
        assert plot_refreshes == [None]


def test_qt_update_emission_failure_does_not_skip_plot_or_success_status(
    qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing Qt emission remains isolated from later accepted-update observers."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(_ContinuumHistory())
    qtbot.addWidget(editor)
    plot_refreshes: list[None] = []
    status_messages: list[str] = []
    editor.status_message.connect(status_messages.append)
    monkeypatch.setattr(editor, "_refresh_plot_display", lambda: plot_refreshes.append(None))

    def fail_qt_emission(_continuum: ContinuumComponent) -> None:
        raise RuntimeError("injected Qt continuum observer failure")

    monkeypatch.setattr(editor, "_emit_continuum_updated", fail_qt_emission)

    editor._run_auto_estimate()

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert continuum.continuum_points
    assert state.current_revision == AnalysisRevision(1)
    assert project.absorption_lines["line-region-1"].needs_optimization is True
    assert plot_refreshes == [None]
    assert status_messages == ["Continuum auto estimate complete"]


def test_identical_continuum_replacement_is_no_change(qtbot: "QtBot") -> None:
    """Replacing points with identical values must not increment revisions."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    history = _ContinuumHistory()
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(history)
    qtbot.addWidget(editor)
    update_notifications: list[ContinuumComponent] = []
    editor.continuum_updated.connect(update_notifications.append)

    editor._apply_continuum_points(continuum.get_continuum_points())

    state = project.region_analysis_state("region-1")
    assert state is not None
    assert state.current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert history.resets == []
    assert update_notifications == []


def test_auto_estimate_auto_create_commits_component_points_and_global_stale(
    qtbot: "QtBot",
) -> None:
    """Auto-estimate without a continuum should commit one combined component command."""
    project = _build_project_without_continuum()
    _add_analysis_region(project, "region-1")
    _add_analysis_region(project, "region-2")
    history = _ContinuumHistory()
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(history)
    qtbot.addWidget(editor)

    editor._run_auto_estimate()

    continua = [
        component
        for component in project.model.components
        if isinstance(component, ContinuumComponent)
    ]
    assert len(continua) == 1
    assert continua[0].continuum_points
    assert history.added_components == [continua[0].id]
    assert history.resets == []
    assert all(
        state.current_revision == AnalysisRevision(1) for state in project.region_analysis_states()
    )
    assert all(line.needs_optimization for line in project.absorption_lines.values())


def test_auto_estimate_auto_create_history_failure_leaves_no_component(qtbot: "QtBot") -> None:
    """A failed combined history record should not leave an empty or guessed component."""
    project = _build_project_without_continuum()
    _add_analysis_region(project, "region-1")
    modified_before = project.modified
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(_ContinuumHistory(fail_component_add=True))
    qtbot.addWidget(editor)

    editor._run_auto_estimate()

    assert not any(
        isinstance(component, ContinuumComponent) for component in project.model.components
    )
    assert project.region_analysis_states()[0].current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert project.modified == modified_before


def test_scientific_mutation_without_history_is_rejected_and_rolled_back(qtbot: "QtBot") -> None:
    """Production continuum edits must not silently run without history wiring."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    qtbot.addWidget(editor)
    before_points = continuum.get_continuum_points()
    status_spy = QSignalSpy(editor.status_message)

    editor.request_add_point(4075.0, 0.9)

    assert continuum.continuum_points == before_points
    assert project.region_analysis_states()[0].current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False
    assert status_spy.count() == 1
    assert "require a connected history recorder" in str(status_spy.at(0)[0]).lower()


def test_auto_estimate_identical_points_is_no_change(
    qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch
) -> None:
    """An identical automatic estimate should not record, stale, or notify UI observers."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    history = _ContinuumHistory()
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(history)
    qtbot.addWidget(editor)
    update_spy = QSignalSpy(editor.continuum_updated)
    status_spy = QSignalSpy(editor.status_message)

    def keep_existing_points(
        candidate: ContinuumComponent,
        _wavelength: npt.NDArray[np.floating],
        _flux: npt.NDArray[np.floating],
        bin_size: float = 100.0,
        cut_level: float = 0.95,
    ) -> None:
        _ = (bin_size, cut_level)
        candidate.continuum_points = continuum.get_continuum_points()

    monkeypatch.setattr(ContinuumComponent, "guess_continuum", keep_existing_points)

    editor._run_auto_estimate()

    assert history.resets == []
    assert update_spy.count() == 0
    assert status_spy.count() == 0
    assert project.region_analysis_states()[0].current_revision == AnalysisRevision(0)
    assert project.absorption_lines["line-region-1"].needs_optimization is False


def test_auto_estimate_observer_failure_keeps_committed_state(
    qtbot: "QtBot", monkeypatch: pytest.MonkeyPatch
) -> None:
    """A post-commit plot observer failure should not revert estimated points or stale state."""
    project, continuum = _build_project_with_continuum()
    _add_analysis_region(project, "region-1")
    editor = ContinuumEditor(project=project)
    editor.set_project(project)
    editor.set_history_recorder(_ContinuumHistory())
    qtbot.addWidget(editor)
    before_points = continuum.get_continuum_points()

    def fail_plot_refresh() -> None:
        raise RuntimeError("injected auto-estimate observer failure")

    monkeypatch.setattr(editor, "_refresh_plot_display", fail_plot_refresh)

    editor._run_auto_estimate()

    assert continuum.continuum_points != before_points
    assert project.region_analysis_states()[0].current_revision == AnalysisRevision(1)
    assert project.absorption_lines["line-region-1"].needs_optimization is True


def test_continuum_editor_uses_qt_source_text(qtbot: "QtBot") -> None:
    """Verify migrated ContinuumEditor UI strings use Qt source text."""
    project, _continuum = _build_project_with_continuum()

    mode_state_store = ModeStateStore(project=project)
    mode_state_store.switch_mode(EditingMode.CONTINUUM)

    editor = ContinuumEditor(project=project, mode_state_store=mode_state_store)
    editor.set_project(project)
    qtbot.addWidget(editor)

    assert editor._actions_title_label is not None
    assert editor._actions_title_label.text() == "Continuum Actions"

    assert editor._anchor_title_label is not None
    assert editor._anchor_title_label.text() == "Control points"

    auto_estimate_button = editor.guess_continuum_btn
    assert auto_estimate_button is not None
    assert auto_estimate_button.text() == "Auto Estimate"
    assert (
        auto_estimate_button.toolTip()
        == "Overwrite current control points with an automatic estimate"
    )

    clear_button = editor.clear_all_btn
    assert clear_button is not None
    assert clear_button.text() == "Clear Control Points"

    table = editor.anchor_points_table
    assert table is not None
    wavelength_header = table.horizontalHeaderItem(editor.COLUMN_WAVELENGTH)
    flux_header = table.horizontalHeaderItem(editor.COLUMN_FLUX)
    assert wavelength_header is not None
    assert wavelength_header.text() == "Wavelength (Å)"
    assert flux_header is not None
    assert flux_header.text() == "Flux"

    assert editor._anchor_placeholder is not None
    assert editor._anchor_placeholder.text() == "Control points will appear here once"

    assert editor._percentile_label is not None
    assert editor._percentile_label.text() == "Percentile"

    assert editor._percentile_spinbox is not None
    assert (
        editor._percentile_spinbox.toolTip()
        == "Percentile threshold for continuum estimation. Higher values (closer to 99%) "
        "capture peaks; lower values (closer to 50%) capture the median."
    )


def test_lupdate_extracts_continuum_editor_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated ContinuumEditor source text."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "gui_continuum_editor_ja.ts"

    run_lupdate(source_dirs=[Path("src/chappy/gui/modes/continuum/editor.py")], ts_output=ts_path)

    root = ET.parse(ts_path).getroot()
    sources = {source.text for source in root.findall(".//source") if source.text is not None}

    assert {
        "Continuum Actions",
        "Control points",
        "Auto Estimate",
        "Overwrite current control points with an automatic estimate",
        "Clear Control Points",
        "Wavelength (Å)",
        "Flux",
        "Control points will appear here once",
        "Percentile",
        (
            "Percentile threshold for continuum estimation. Higher values (closer to 99%) "
            "capture peaks; lower values (closer to 50%) capture the median."
        ),
        "Yes",
        "No",
        "Loading...",
        "No observation data available for continuum fitting",
        "Continuum auto estimate complete",
        "Continuum auto estimate failed",
        "Overwrite existing continuum points?",
        "Clears all custom control points and restores defaults. Continue?",
        "Duplicate Wavelength",
        "A control point already exists at wavelength {wavelength} Å.\n"
        "Wavelengths must be unique.",
        "Minimum Control Points Required",
        "The continuum requires at least 3 control points.\n"
        "Deletion was cancelled to keep 3 points.",
    } <= sources
    assert not any("MSG__" in source for source in sources)
    assert not any("DLG__" in source for source in sources)
    assert not any("GUI__" in source for source in sources)


def test_lupdate_extracts_matplotlib_continuum_editor_sources(tmp_path: Path) -> None:
    """Verify lupdate extracts migrated MatplotlibContinuumEditor sources."""
    if shutil.which("pyside6-lupdate") is None:
        pytest.skip("pyside6-lupdate is not available")

    ts_path = tmp_path / "continuum_editor_ja.ts"

    run_lupdate(
        source_dirs=[Path("src/chappy/plotting/components/continuum_editor.py")], ts_output=ts_path
    )

    root = ET.parse(ts_path).getroot()
    sources = {source.text for source in root.findall(".//source") if source.text is not None}

    assert sources == {
        "Add Control Point",
        "Delete Control Point",
        "λ = {wavelength:.2f} Å\nFlux = {flux:.3f}",
    }
    assert not any("GUI__" in source for source in sources)
