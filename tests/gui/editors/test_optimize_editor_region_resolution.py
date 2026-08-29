"""Tests for OptimizeEditor active-region resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.editor import OptimizeEditor

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _editor(qtbot: QtBot) -> OptimizeEditor:
    editor = OptimizeEditor()
    qtbot.addWidget(editor)
    return editor


def test_without_provider_resolves_no_region(qtbot: QtBot) -> None:
    """Without a provider there is no active region."""
    editor = _editor(qtbot)

    assert editor._resolve_active_region_id() is None


def test_provider_supplies_region(qtbot: QtBot) -> None:
    """The Detail panel's selection must drive fit region resolution."""
    editor = _editor(qtbot)

    editor.set_active_region_id_provider(lambda: "region-1")
    assert editor._resolve_active_region_id() == "region-1"

    editor.set_active_region_id_provider(lambda: None)
    assert editor._resolve_active_region_id() is None

    editor.set_active_region_id_provider(None)
    assert editor._resolve_active_region_id() is None


def _project_with_region() -> SpectroscopyProject:
    project = SpectroscopyProject()
    line = AbsorptionLine(
        line_id="line-1",
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.0,
        window_kms=150.0,
        region_id="region-1",
        multiplet_label="",
        transition_name="H I 1215.7",
        oscillator_strength=0.4164,
        gamma_value=6.265e8,
    )
    project.absorption_lines[line.line_id] = line
    project.absorption_regions["region-1"] = AbsorptionRegion(
        region_id="region-1", line_ids=[line.line_id]
    )
    return project


def test_fit_wavelength_range_follows_provider_region(qtbot: QtBot) -> None:
    """The fit range must come from the provider-resolved region, not the legacy combo."""
    editor = _editor(qtbot)
    editor.set_project(_project_with_region())
    editor.mode_state_store = SimpleNamespace(current_mode=EditingMode.ANALYSIS)  # type: ignore[assignment]

    editor.set_active_region_id_provider(lambda: "region-1")
    fit_range = editor._get_fitting_wavelength_range()
    assert fit_range is not None
    low, high = fit_range
    observed_center = 1215.67 * 2.0
    assert low < observed_center < high

    editor.set_active_region_id_provider(lambda: None)
    assert editor._get_fitting_wavelength_range() is None
