"""Adapter for optimize model mutation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from chappy.application.history.snapshot_mapping import ModelLink
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.spectroscopy_project import SpectroscopyProject


class OptimizeModelMutationAdapter:
    """Resolve model mutation targets and link snapshots for optimize mode."""

    def build_links_for_components(
        self, project: SpectroscopyProject | None, components: list[AbsorberComponent]
    ) -> list[ModelLink]:
        """Build component-to-line links with stable positions.

        Args:
            project: Current project.
            components: Components to snapshot.

        Returns:
            Link snapshots used by history commands.
        """
        if project is None:
            return []
        links: list[ModelLink] = []
        for component in components:
            for line in project.absorption_lines.values():
                if component.id in line.model_ids:
                    index = line.model_ids.index(component.id)
                    links.append(
                        {"line_id": line.line_id, "component_id": component.id, "index": index}
                    )
                    break
        return links

    def collect_delete_targets(
        self,
        components: Iterable[AbsorberComponent],
        expand_component: Callable[[AbsorberComponent], list[AbsorberComponent]],
    ) -> list[AbsorberComponent]:
        """Collect unique delete targets from explicit components.

        Args:
            components: Components explicitly targeted by the user.
            expand_component: Function that resolves linked multiplet components.

        Returns:
            Unique components to delete.
        """
        targets: list[AbsorberComponent] = []
        seen: set[str] = set()
        for component in components:
            for candidate in expand_component(component):
                if candidate.id in seen:
                    continue
                seen.add(candidate.id)
                targets.append(candidate)
        return targets
