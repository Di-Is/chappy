"""Tests for optimize velocity plot controller."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.editing_mode import EditingMode
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail import (
    OptimizeVelocityOverlayContext,
    OptimizeVelocityPlotController,
    OptimizeVelocityPlotPorts,
)


@dataclass(slots=True)
class _Harness:
    """Controller harness with captured shell callbacks."""

    controller: OptimizeVelocityPlotController
    shown_contexts: list[OptimizeVelocityOverlayContext]
    hide_events: list[bool]
    checked_states: list[bool]


def _project_with_region() -> tuple[SpectroscopyProject, str]:
    """Create a project with one optimize region and one model component."""
    project = SpectroscopyProject()
    region_id = "region-1"
    line = AbsorptionLine(
        line_id="line-1",
        species="H I",
        rest_wavelength=1215.67,
        center_z=1.5,
        window_kms=180.0,
        region_id=region_id,
        multiplet_ids=[],
        model_ids=["component-1"],
        multiplet_label="",
        transition_name="H I 1215.7",
        oscillator_strength=0.1,
        gamma_value=1e8,
    )
    component = AbsorberComponent(
        component_id="component-1", name="component-1", wavelength=1215.67, redshift=1.51
    )
    project.absorption_lines[line.line_id] = line
    project.absorption_regions[region_id] = AbsorptionRegion(
        region_id=region_id, line_ids=[line.line_id]
    )
    project.model.add_component(component)
    return project, region_id


def _harness(
    project: SpectroscopyProject,
    region_id: str,
    *,
    mode: EditingMode = EditingMode.ANALYSIS,
    visible: bool = False,
) -> _Harness:
    """Create a controller harness."""
    shown_contexts: list[OptimizeVelocityOverlayContext] = []
    checked_states: list[bool] = []
    hide_events: list[bool] = []

    def hide() -> None:
        hide_events.append(True)

    controller = OptimizeVelocityPlotController(
        OptimizeVelocityPlotPorts(
            current_mode_provider=lambda: mode,
            project_provider=lambda: project,
            selected_region_id_provider=lambda: region_id,
            velocity_visible_provider=lambda: visible,
            show_velocity_plot_callback=shown_contexts.append,
            hide_velocity_plot_callback=hide,
            action_checked_callback=checked_states.append,
        )
    )
    return _Harness(
        controller=controller,
        shown_contexts=shown_contexts,
        hide_events=hide_events,
        checked_states=checked_states,
    )


def test_build_context_from_selected_region() -> None:
    """Controller should build a mode-local velocity overlay context."""
    project, region_id = _project_with_region()
    harness = _harness(project, region_id)

    context = harness.controller.build_context()

    assert context is not None
    assert context.center_z == pytest.approx(1.5)
    assert context.region_id == region_id
    assert len(context.slices) == 1
    assert context.slices[0].region_id == region_id
    assert context.slices[0].analysis_half_width_kms == pytest.approx(180.0)
    assert context.slices[0].components[0].component_id == "component-1"


def test_toggle_shows_when_hidden_in_optimize_mode() -> None:
    """Toggle should show the optimize velocity plot when hidden."""
    project, region_id = _project_with_region()
    harness = _harness(project, region_id)

    harness.controller.toggle()

    assert len(harness.shown_contexts) == 1
    assert harness.checked_states == [True]


def test_toggle_hides_when_visible() -> None:
    """Toggle should hide the optimize velocity plot when visible."""
    project, region_id = _project_with_region()
    harness = _harness(project, region_id, visible=True)

    harness.controller.toggle()

    assert harness.hide_events == [True]
    assert harness.checked_states == [False]


def test_toggle_ignores_non_optimize_mode() -> None:
    """Toggle should do nothing outside optimize mode."""
    project, region_id = _project_with_region()
    harness = _harness(project, region_id, mode=EditingMode.IDENTIFY)

    harness.controller.toggle()

    assert harness.shown_contexts == []
    assert harness.hide_events == []
    assert harness.checked_states == []
