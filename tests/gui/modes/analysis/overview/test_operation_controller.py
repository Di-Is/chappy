"""Tests for organize structure-operation availability and preview routing."""

from __future__ import annotations

from chappy.application.organize import OrganizeOperationUseCase
from chappy.application.structure import StructureImpactOperation
from chappy.core.absorption.models import AbsorptionLine, AbsorptionRegion
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.overview.adapters import OrganizeOperationAdapter
from chappy.gui.modes.analysis.overview.operation_controller import OrganizeOperationController


def _line(line_id: str, *, linked_to: str | None = None) -> AbsorptionLine:
    """Create one line for controller boundary tests."""
    return AbsorptionLine(
        line_id=line_id,
        species="Mg II",
        rest_wavelength=2796.0,
        center_z=1.0,
        window_kms=150.0,
        multiplet_label="Mg II",
        transition_name=line_id,
        oscillator_strength=0.6,
        gamma_value=1.0e8,
        multiplet_ids=[linked_to] if linked_to is not None else [],
        region_id="region",
    )


def _project() -> SpectroscopyProject:
    """Create one linked pair and one independent line."""
    project = SpectroscopyProject()
    project.absorption_lines.update(
        {
            "blue": _line("blue", linked_to="red"),
            "red": _line("red", linked_to="blue"),
            "single": _line("single"),
        }
    )
    project.absorption_regions["region"] = AbsorptionRegion(
        region_id="region", line_ids=["blue", "red", "single"]
    )
    return project


def _controller() -> OrganizeOperationController:
    """Create the real controller/use-case boundary."""
    return OrganizeOperationController(
        operation_adapter=OrganizeOperationAdapter(OrganizeOperationUseCase())
    )


def test_unlink_is_available_only_for_one_materialized_line_system() -> None:
    """Mixed, independent, missing, and absent selections cannot unlink."""
    project = _project()
    controller = _controller()

    assert controller.can_unlink(project, [], ["blue"]) is True
    assert controller.can_unlink(project, ["region"], ["blue"]) is False
    assert controller.can_unlink(project, [], ["single"]) is False
    assert controller.can_unlink(project, [], ["missing"]) is False
    assert controller.can_unlink(project, [], []) is False
    assert controller.can_unlink(None, [], ["blue"]) is False


def test_unlink_preview_reports_exact_expanded_system_without_mutation() -> None:
    """Controller delegates to the shared typed preview and stays side-effect free."""
    project = _project()
    controller = _controller()

    preview = controller.preview_unlink(project, system_ids=["blue"])

    assert preview is not None
    assert preview.operation is StructureImpactOperation.UNLINK
    assert preview.expanded_request_line_ids == ("blue", "red")
    assert preview.changed_line_ids == ("blue", "red")
    assert project.absorption_lines["blue"].multiplet_ids == ["red"]
    assert project.absorption_lines["red"].multiplet_ids == ["blue"]


def test_independent_line_unlink_preview_is_no_change() -> None:
    """An independent line stops before confirmation or mutation routing."""
    statuses: list[str] = []
    controller = OrganizeOperationController(
        operation_adapter=OrganizeOperationAdapter(OrganizeOperationUseCase()),
        status_callback=statuses.append,
    )

    assert controller.preview_unlink(_project(), system_ids=["single"]) is None
    assert statuses
