"""Port adapter backed by named model-addition collaborators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.gui.modes.analysis.region_detail.model_addition_controller import (
    model_addition_wavelength_range_for_line,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.components.absorber import AbsorberComponent
    from chappy.core.components.tie_set import ParameterTieSet
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.analysis.region_detail.adapters.history_adapter import (
        OptimizeHistoryAdapter,
    )
    from chappy.gui.modes.analysis.region_detail.state import RegionDetailViewState


@dataclass(frozen=True, slots=True)
class OptimizeModelAdditionPortAdapter:
    """Adapt named collaborators for model addition."""

    project_provider: Callable[[], SpectroscopyProject | None]
    view_state: RegionDetailViewState
    history_adapter: OptimizeHistoryAdapter
    finalise_model_addition_display: Callable[..., None]

    def selected_model_addition_line(self) -> AbsorptionLine | None:
        """Return the currently selected absorption line."""
        return self.view_state.resolve_selected_line(self.project_provider())

    def model_addition_project(self) -> SpectroscopyProject | None:
        """Return the active project."""
        return self.project_provider()

    def line_wavelength_range_for_model_addition(
        self, line: AbsorptionLine
    ) -> tuple[float, float] | None:
        """Return the observed wavelength range accepted for a line."""
        return model_addition_wavelength_range_for_line(line)

    def record_model_addition(
        self, components: dict[str, AbsorberComponent], tie_sets: tuple[ParameterTieSet, ...]
    ) -> None:
        """Record model components added by the workflow."""
        self.history_adapter.record_add(components, tie_sets)

    def finalise_model_addition(
        self, components: dict[str, AbsorberComponent], *, focus_line: AbsorptionLine
    ) -> None:
        """Refresh UI state after adding model components."""
        self.finalise_model_addition_display(components, focus_line=focus_line)

    def model_addition_history_atomic_recording(self) -> AbstractContextManager[None]:
        """Return the required atomic history scope."""
        return self.history_adapter.atomic_recording()
