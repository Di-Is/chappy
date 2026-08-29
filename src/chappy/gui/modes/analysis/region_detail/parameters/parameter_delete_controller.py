"""Controller for atomic Optimize component deletion."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chappy.application.analysis_artifacts import GlobalAnalysisMutationUseCase
from chappy.application.optimize import (
    AbsorberModelTopologyUseCase,
    DeleteOptimizeModelComponentsUseCase,
    ModelDeletionHistorySnapshot,
    component_topology_change_set,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from contextlib import AbstractContextManager

    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.spectroscopy_project import SpectroscopyProject


class OptimizeParameterDeletePort(Protocol):
    """History operations required by component deletion."""

    def record_delete_components(self, snapshot: ModelDeletionHistorySnapshot) -> None:
        """Record the immutable pre-delete history payload."""
        ...

    def delete_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return the required atomic history scope."""
        ...


class OptimizeParameterDeleteController:
    """Delete Optimize model components in one global scientific transaction."""

    def __init__(
        self,
        *,
        port: OptimizeParameterDeletePort,
        usecase: DeleteOptimizeModelComponentsUseCase | None = None,
        topology: AbsorberModelTopologyUseCase | None = None,
        mutations: GlobalAnalysisMutationUseCase | None = None,
    ) -> None:
        """Initialize the controller and its application mutation seams."""
        self._port = port
        self._usecase = usecase or DeleteOptimizeModelComponentsUseCase()
        self._topology = topology or AbsorberModelTopologyUseCase()
        self._mutations = mutations or GlobalAnalysisMutationUseCase()

    def delete_components(
        self, project: SpectroscopyProject | None, components: Iterable[AbsorberComponent]
    ) -> bool:
        """Delete unique existing components and return whether the commit changed state."""
        if project is None:
            return False

        unique_components = self._unique_components(components)
        existing = tuple(
            component for component in unique_components if component in project.model.components
        )
        if not existing:
            return False

        topology_before = self._topology.capture(project, additional_components=existing)
        history_before = self._topology.capture_deletion_history(project, existing)

        def mutate() -> bool:
            return self._usecase.delete_components(project, existing)

        impact = self._mutations.execute(
            project,
            mutate=mutate,
            rollback=lambda: self._topology.restore(project, topology_before),
            record_history=lambda: self._port.record_delete_components(history_before),
            history_scope=self._port.delete_history_atomic_recording,
            postcommit_changes=lambda: component_topology_change_set(
                removed_ids=tuple(component.id for component in existing)
            ),
        )
        return impact.changed

    @staticmethod
    def _unique_components(
        components: Iterable[AbsorberComponent],
    ) -> tuple[AbsorberComponent, ...]:
        """Return components de-duplicated by id while preserving order."""
        unique: dict[str, AbsorberComponent] = {}
        for component in components:
            unique.setdefault(component.id, component)
        return tuple(unique.values())
