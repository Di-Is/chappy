"""Atomic continuum component mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import (
    AnalysisMutationImpact,
    GlobalAnalysisMutationProjectPort,
    GlobalAnalysisMutationUseCase,
)
from chappy.core.change_set import ChangeSet
from chappy.core.components.continuum import ContinuumComponent
from chappy.core.events import ComponentAdded, ModelInvalidated, ModelUpdated

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chappy.core.spectrum_model import SpectrumModel


class ContinuumComponentMutationProjectPort(GlobalAnalysisMutationProjectPort, Protocol):
    """Project operations required by continuum component creation."""

    model: SpectrumModel


@dataclass(frozen=True, slots=True)
class ContinuumComponentAddResult:
    """Committed continuum component and its global analysis impact."""

    component: ContinuumComponent
    impact: AnalysisMutationImpact


class ContinuumComponentMutationUseCase:
    """Create continuum components as atomic scientific commands."""

    def __init__(self, *, mutations: GlobalAnalysisMutationUseCase | None = None) -> None:
        """Initialize with the global scientific mutation transaction."""
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    def add_component(
        self,
        project: ContinuumComponentMutationProjectPort,
        *,
        name: str,
        points: list[tuple[float, float]],
        record_history: Callable[[ContinuumComponent], None],
        history_scope: Callable[[], AbstractContextManager[None]],
    ) -> ContinuumComponentAddResult:
        """Create a component, invalidate analysis, and record one history command."""
        component = ContinuumComponent(name=name)
        component.continuum_points = list(points)
        impact = self._mutations.execute(
            project,
            mutate=lambda: self._add_component(project, component),
            rollback=lambda: self._remove_component(project, component),
            record_history=lambda: record_history(component),
            history_scope=history_scope,
            postcommit_changes=lambda: ChangeSet.of(
                ComponentAdded(component_id=component.id), ModelInvalidated(), ModelUpdated()
            ),
        )
        return ContinuumComponentAddResult(component=component, impact=impact)

    @staticmethod
    def _add_component(
        project: ContinuumComponentMutationProjectPort, component: ContinuumComponent
    ) -> bool:
        """Add a newly constructed component to the scientific model."""
        if component in project.model.components:
            return False
        project.model.add_component_storage(component)
        return True

    @staticmethod
    def _remove_component(
        project: ContinuumComponentMutationProjectPort, component: ContinuumComponent
    ) -> None:
        """Remove a partially committed component during rollback."""
        if component in project.model.components:
            project.model.remove_component_storage(component)


__all__ = [
    "ContinuumComponentAddResult",
    "ContinuumComponentMutationProjectPort",
    "ContinuumComponentMutationUseCase",
]
