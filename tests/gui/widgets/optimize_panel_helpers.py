"""Test helpers for optimize mode panel construction."""

from __future__ import annotations

from chappy.application.optimize import ModelAdditionRequest, ModelAdditionResult
from chappy.core.absorption.models import AbsorptionLine
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.modes.analysis.region_detail.composition import (
    MULTIPLET_REDSHIFT_TOLERANCE,
    OptimizeParameterMutationUseCase,
    TieSetEditUseCase,
    create_optimize_parameter_mutation_usecase,
    create_optimize_tie_set_edit_usecase,
)


class NoOpModelAdditionUseCase:
    """No-op model-addition use case for panel tests unrelated to model creation."""

    def add_components(
        self, project: SpectroscopyProject, line: AbsorptionLine, request: ModelAdditionRequest
    ) -> ModelAdditionResult:
        """Return an empty model-addition result."""
        _ = project, line, request
        return ModelAdditionResult(components_by_line_id={}, tie_sets=())


def build_region_detail_usecases() -> tuple[OptimizeParameterMutationUseCase, TieSetEditUseCase]:
    """Build the panel's required parameter-mutation and tie-set-edit use cases."""
    parameter_mutation_usecase = create_optimize_parameter_mutation_usecase()
    tie_set_edit_usecase = create_optimize_tie_set_edit_usecase(
        redshift_tolerance=MULTIPLET_REDSHIFT_TOLERANCE,
        parameter_mutation=parameter_mutation_usecase,
    )
    return parameter_mutation_usecase, tie_set_edit_usecase


class AnalysisFocusRecorder:
    """Record canonical region focus requests from the legacy Optimize panel."""

    def __init__(self) -> None:
        self.region_ids: list[str] = []
        self._focused_region_id: str | None = None
        self.clear_focus_if_calls: list[str] = []
        self.clear_focus_only_if_calls: list[str] = []

    def focus_region(self, region_id: str) -> bool:
        """Record a region focus request and update the canonical focus."""
        self.region_ids.append(region_id)
        self._focused_region_id = region_id
        return True

    def focused_region_id(self) -> str | None:
        """Return the canonical focused region ID, matching the last `focus_region` call."""
        return self._focused_region_id

    def clear_focus_if(self, region_id: str) -> None:
        """Clear the recorded canonical focus (and, in the real port, the surface)."""
        self.clear_focus_if_calls.append(region_id)
        if self._focused_region_id == region_id:
            self._focused_region_id = None

    def clear_focus_only_if(self, region_id: str) -> None:
        """Clear the recorded canonical focus without touching the surface."""
        self.clear_focus_only_if_calls.append(region_id)
        if self._focused_region_id == region_id:
            self._focused_region_id = None
