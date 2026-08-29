"""Qt-free tests for RegionDetailViewState."""

from __future__ import annotations

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.state import RegionDetailViewState
from chappy.presentation.optimize import FitChi2View, FitReadyView


def _line(line_id: str, *, region_id: str | None) -> AbsorptionLine:
    return AbsorptionLine(
        line_id=line_id,
        species="HI",
        rest_wavelength=1215.67,
        center_z=0.0,
        window_kms=100.0,
        multiplet_label="HI 1215",
        transition_name="HI 1215",
        oscillator_strength=0.4164,
        gamma_value=6.265e8,
        region_id=region_id,
    )


def _project_with_line(line: AbsorptionLine, *, region_id: str) -> SpectroscopyProject:
    project = SpectroscopyProject()
    project.absorption_lines[line.line_id] = line
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=[line.line_id]
    )
    return project


def test_reset_for_project_change_clears_both_fields_atomically() -> None:
    state = RegionDetailViewState()
    state.set_selected_line_id("line-1")
    state.set_fit_status(FitChi2View(chi2=1.5, reduced=None))

    state.reset_for_project_change()

    assert state.selected_line_id is None
    assert state.fit_status == FitReadyView()


def test_clear_selection_outside_region_clears_when_line_belongs_elsewhere() -> None:
    line = _line("line-1", region_id="region-a")
    project = _project_with_line(line, region_id="region-a")
    state = RegionDetailViewState(selected_line_id="line-1")

    cleared = state.clear_selection_outside_region(project, "region-b")

    assert cleared is True
    assert state.selected_line_id is None


def test_clear_selection_outside_region_keeps_selection_inside_region() -> None:
    line = _line("line-1", region_id="region-a")
    project = _project_with_line(line, region_id="region-a")
    state = RegionDetailViewState(selected_line_id="line-1")

    cleared = state.clear_selection_outside_region(project, "region-a")

    assert cleared is False
    assert state.selected_line_id == "line-1"


def test_drop_vanished_selection_clears_when_line_no_longer_exists() -> None:
    project = SpectroscopyProject()
    state = RegionDetailViewState(selected_line_id="line-gone")

    cleared = state.drop_vanished_selection(project)

    assert cleared is True
    assert state.selected_line_id is None


def test_drop_vanished_selection_keeps_selection_when_line_still_exists() -> None:
    line = _line("line-1", region_id="region-a")
    project = _project_with_line(line, region_id="region-a")
    state = RegionDetailViewState(selected_line_id="line-1")

    cleared = state.drop_vanished_selection(project)

    assert cleared is False
    assert state.selected_line_id == "line-1"


def test_resolve_selected_line_returns_current_line_through_project() -> None:
    line = _line("line-1", region_id="region-a")
    project = _project_with_line(line, region_id="region-a")
    state = RegionDetailViewState(selected_line_id="line-1")

    assert state.resolve_selected_line(project) is line


def test_resolve_selected_line_returns_none_without_selection() -> None:
    state = RegionDetailViewState()

    assert state.resolve_selected_line(SpectroscopyProject()) is None


def test_resolve_selected_line_returns_none_without_project() -> None:
    state = RegionDetailViewState(selected_line_id="line-1")

    assert state.resolve_selected_line(None) is None
