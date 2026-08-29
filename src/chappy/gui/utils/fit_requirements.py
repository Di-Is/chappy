"""Shared helpers for optimization fit prerequisites."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.core.components.absorber import AbsorberComponent

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject


def region_has_models(project: SpectroscopyProject | None, region_id: str | None) -> bool:
    """Return whether the selected region has at least one absorber component.

    Args:
        project: Active project instance.
        region_id: Identifier of the currently selected absorption region.

    Returns:
        True when an observed spectrum is loaded and the region owns an
        absorber component; otherwise False.
    """
    if project is None:
        return False

    model = project.model
    if model is None or model.observed_spectrum is None:
        return False

    if not isinstance(region_id, str) or not region_id:
        return False

    region = project.absorption_regions.get(region_id)
    if region is None:
        return False

    for line_id in region.line_ids:
        line = project.absorption_lines.get(line_id)
        if line is None:
            continue

        model_ids = line.model_ids
        if not model_ids:
            continue

        for model_id in model_ids:
            component = project.find_absorber_component(model_id)
            if isinstance(component, AbsorberComponent):
                return True

    return False
