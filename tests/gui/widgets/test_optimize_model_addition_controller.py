"""Tests for optimize model addition controller."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

import pytest

from chappy.application.optimize import ModelAdditionRequest
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.analysis import AnalysisRevision
from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
    OptimizeModelAdditionController,
)


def _line(line_id: str = "line-a") -> AbsorptionLine:
    """Build an absorption line for model-addition controller tests."""
    return AbsorptionLine(
        line_id=line_id,
        species="X",
        rest_wavelength=1000.0,
        center_z=1.0,
        window_kms=150.0,
        multiplet_label="",
        transition_name="X 1000",
        oscillator_strength=0.0,
        gamma_value=0.0,
    )


@dataclass(frozen=True, slots=True)
class _AdditionResult:
    """Fake model-addition result."""

    components_by_line_id: dict[str, AbsorberComponent]
    tie_sets: tuple[object, ...] = ()


class _UseCase:
    """Fake model-addition use case."""

    def __init__(self) -> None:
        """Initialize captured requests."""
        self.requests: list[tuple[SpectroscopyProject, AbsorptionLine, ModelAdditionRequest]] = []

    def add_components(
        self, project: SpectroscopyProject, line: AbsorptionLine, request: ModelAdditionRequest
    ) -> _AdditionResult:
        """Record request and return a created component."""
        self.requests.append((project, line, request))
        component = AbsorberComponent(name="X", wavelength=line.rest_wavelength)
        project.model.add_component_storage(component)
        line.model_ids.append(component.id)
        return _AdditionResult(components_by_line_id={line.line_id: component})


class _Port:
    """Fake model-addition port."""

    def __init__(self) -> None:
        """Initialize captured calls."""
        self.line = _line()
        self.project = SpectroscopyProject()
        self.project.absorption_lines[self.line.line_id] = self.line
        self.bounds: tuple[float, float] | None = (1900.0, 2100.0)
        self.recorded: list[dict[str, AbsorberComponent]] = []
        self.finalised: list[tuple[dict[str, AbsorberComponent], AbsorptionLine]] = []
        self.fail_record = False
        self.fail_finalise = False
        self.atomic_entries = 0

    def selected_model_addition_line(self) -> AbsorptionLine | None:
        """Return selected line."""
        return self.line

    def model_addition_project(self) -> SpectroscopyProject | None:
        """Return active project."""
        return self.project

    def line_wavelength_range_for_model_addition(
        self, line: AbsorptionLine
    ) -> tuple[float, float] | None:
        """Return accepted wavelength bounds."""
        return self.bounds

    def record_model_addition(
        self, components: dict[str, AbsorberComponent], tie_sets: tuple[object, ...]
    ) -> None:
        """Record created components."""
        del tie_sets
        if self.fail_record:
            raise RuntimeError("injected model addition history failure")
        self.recorded.append(components)

    @contextlib.contextmanager
    def model_addition_history_atomic_recording(self):
        """Record one atomic history boundary."""
        self.atomic_entries += 1
        yield

    def finalise_model_addition(
        self, components: dict[str, AbsorberComponent], *, focus_line: AbsorptionLine
    ) -> None:
        """Record finalization."""
        if self.fail_finalise:
            raise RuntimeError("injected model addition finalise failure")
        self.finalised.append((components, focus_line))


def test_add_to_selected_line_uses_line_center_redshift() -> None:
    """Default add action uses the selected line center redshift."""
    port = _Port()
    usecase = _UseCase()
    controller = OptimizeModelAdditionController(port, usecase=usecase)

    controller.add_to_selected_line()

    assert len(usecase.requests) == 1
    assert usecase.requests[0][2].redshift == 1.0
    assert len(port.recorded) == 1
    assert len(port.finalised) == 1
    assert port.atomic_entries == 1


def test_controller_requires_model_addition_usecase() -> None:
    """Model-addition use case is a required composition dependency."""
    with pytest.raises(TypeError, match="usecase"):
        OptimizeModelAdditionController(_Port())


def test_add_to_selected_line_requires_active_project() -> None:
    """A selected line without an active project is an internal state error."""
    port = _Port()
    port.project = None
    controller = OptimizeModelAdditionController(port, usecase=_UseCase())

    with pytest.raises(RuntimeError, match="Active project is required"):
        controller.add_to_selected_line()


def test_add_at_wavelength_rejects_outside_bounds() -> None:
    """Shift-click add ignores wavelengths outside the selected line range."""
    port = _Port()
    usecase = _UseCase()
    controller = OptimizeModelAdditionController(port, usecase=usecase)

    controller.add_at_wavelength(2200.0)

    assert usecase.requests == []
    assert port.recorded == []
    assert port.finalised == []


def test_add_at_wavelength_calculates_redshift() -> None:
    """Shift-click add converts observed wavelength to redshift."""
    port = _Port()
    usecase = _UseCase()
    controller = OptimizeModelAdditionController(port, usecase=usecase)

    controller.add_at_wavelength(2000.0)

    assert len(usecase.requests) == 1
    assert usecase.requests[0][2].redshift == 1.0
    assert len(port.recorded) == 1
    assert len(port.finalised) == 1


def test_add_from_velocity_line_id_resolves_project_line() -> None:
    """Velocity add resolves the line id before creating components."""
    port = _Port()
    usecase = _UseCase()
    controller = OptimizeModelAdditionController(port, usecase=usecase)

    controller.add_from_velocity_line_id(
        velocity=0.0, line_id=port.line.line_id, rest_wavelength=1000.0, center_z=1.5
    )

    assert len(usecase.requests) == 1
    assert usecase.requests[0][1] is port.line
    assert usecase.requests[0][2].redshift == 1.5
    assert len(port.recorded) == 1


def test_model_addition_history_failure_restores_exact_topology() -> None:
    """A history failure removes the added component and restores line freshness."""
    port = _Port()
    port.line.region_id = "region-1"
    port.project.absorption_regions["region-1"] = AbsorptionRegion(
        region_id="region-1", line_ids=[port.line.line_id]
    )
    port.fail_record = True
    controller = OptimizeModelAdditionController(port, usecase=_UseCase())

    with pytest.raises(RuntimeError, match="injected model addition history failure"):
        controller.add_to_selected_line()

    assert not any(
        isinstance(component, AbsorberComponent) for component in port.project.model.components
    )
    assert port.line.model_ids == []
    assert port.line.needs_optimization is False
    assert port.project.region_analysis_state("region-1").current_revision == AnalysisRevision(0)
    assert port.finalised == []


def test_model_addition_observer_failure_keeps_commit_and_reaches_ui_refresh() -> None:
    """An isolated observer failure keeps the commit and reaches later work."""
    port = _Port()
    port.line.region_id = "region-1"
    port.project.absorption_regions["region-1"] = AbsorptionRegion(
        region_id="region-1", line_ids=[port.line.line_id]
    )
    later_events: list[object] = []

    def fail_observer(_changes: object) -> None:
        raise RuntimeError("injected model addition observer failure")

    port.project.model.events.subscribe(fail_observer)
    port.project.model.events.subscribe(later_events.append)
    controller = OptimizeModelAdditionController(port, usecase=_UseCase())

    controller.add_to_selected_line()

    assert len(port.line.model_ids) == 1
    assert port.project.find_absorber_component(port.line.model_ids[0]) is not None
    assert port.project.region_analysis_state("region-1").current_revision == AnalysisRevision(1)
    assert len(port.recorded) == 1
    assert len(later_events) == 1
    assert len(port.finalised) == 1


def test_model_addition_finalise_failure_does_not_escape_after_commit() -> None:
    """A failed final UI refresh must not make an accepted addition look rejected."""
    port = _Port()
    port.fail_finalise = True
    controller = OptimizeModelAdditionController(port, usecase=_UseCase())

    controller.add_to_selected_line()

    assert len(port.line.model_ids) == 1
    assert port.project.find_absorber_component(port.line.model_ids[0]) is not None
    assert len(port.recorded) == 1
    assert port.finalised == []
