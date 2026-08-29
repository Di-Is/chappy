"""Application use case for deleting Optimize absorber model components."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.tie_set import ParameterTieSet
    from chappy.core.spectroscopy_project import SpectroscopyProject


class DeleteOptimizeModelComponentsUseCase:
    """Delete absorber components and normalize their parameter tie topology."""

    def delete_components(
        self, project: SpectroscopyProject, components: tuple[AbsorberComponent, ...]
    ) -> bool:
        """Delete existing components and return whether topology changed."""
        existing = tuple(
            component for component in components if component in project.model.components
        )
        if not existing:
            return False

        deleted_ids = {component.id for component in existing}
        tie_sets_to_cleanup = {
            component.tie_set for component in existing if component.tie_set is not None
        }

        for component in existing:
            self._detach_component_from_lines(project, component)
            project.model.remove_component_storage(component)

        for tie_set in tie_sets_to_cleanup:
            self._cleanup_tie_set_after_delete(project, tie_set, deleted_ids, existing)
        return True

    def _cleanup_tie_set_after_delete(
        self,
        project: SpectroscopyProject,
        tie_set: ParameterTieSet,
        deleted_ids: set[str],
        deleted_components: tuple[AbsorberComponent, ...],
    ) -> None:
        """Synchronize a tie set after deleting some of its components."""
        tie_set.components[:] = [
            component for component in tie_set.components if component.id not in deleted_ids
        ]
        if tie_set.parent_tie is not None:
            tie_set.parent_tie.components[:] = [
                component
                for component in tie_set.parent_tie.components
                if component.id not in deleted_ids
            ]
        for component in deleted_components:
            if component.tie_set is tie_set:
                component.tie_set = None

        if tie_set.participation_unit_count() >= 2:
            return

        parent = tie_set.parent_tie
        if parent is not None:
            parent.detach_tie_set(tie_set)
        self._dissolve_tie_set(project, tie_set)

        if parent is not None and parent.participation_unit_count() <= 1:
            self._dissolve_tie_set(project, parent)

    def _dissolve_tie_set(self, project: SpectroscopyProject, tie_set: ParameterTieSet) -> None:
        """Dissolve a tie set without treating nested components as direct members."""
        for nested_uid in tuple(tie_set.member_uids):
            nested = next(
                (
                    candidate
                    for candidate in project.model.iter_tie_sets()
                    if candidate.uid == nested_uid and candidate.parent_tie is tie_set
                ),
                None,
            )
            if nested is not None:
                tie_set.detach_tie_set(nested)
        for leftover in tuple(
            component for component in tie_set.components if component.tie_set is tie_set
        ):
            tie_set.remove_component(leftover)
        project.model.remove_tie_set(tie_set)

    @staticmethod
    def _detach_component_from_lines(
        project: SpectroscopyProject, component: AbsorberComponent
    ) -> None:
        """Detach one component from every linked absorption line."""
        for line in project.absorption_lines.values():
            if component.id not in line.model_ids:
                continue
            line.model_ids.remove(component.id)
            if not line.model_ids:
                line.needs_optimization = False


__all__ = ["DeleteOptimizeModelComponentsUseCase"]
