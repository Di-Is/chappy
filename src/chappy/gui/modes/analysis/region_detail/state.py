"""Region Detail UI projection state.

`RegionDetailViewState` is not a new source of truth for any project-level
fact; it holds only the display-local projection facts that Region Detail
UI needs across refreshes (see the state ownership table in
`docs/task/region-detail-panel-decomposition/target-architecture.md`):
which line the tree selected (by id, resolved through the project at use
time) and the most recent fit workflow display status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from chappy.presentation.optimize import FitReadyView

if TYPE_CHECKING:
    from chappy.core.absorption.models import AbsorptionLine
    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.presentation.optimize import FitStatusView


@dataclass(slots=True)
class RegionDetailViewState:
    """Region Detail UI's selected-line and fit-display projection state."""

    selected_line_id: str | None = None
    fit_status: FitStatusView = field(default_factory=FitReadyView)

    def set_selected_line_id(self, line_id: str | None) -> None:
        """Set the selected line id, or clear the selection with ``None``."""
        self.selected_line_id = line_id

    def set_fit_status(self, status: FitStatusView) -> None:
        """Set the fit workflow display status."""
        self.fit_status = status

    def resolve_selected_line(self, project: SpectroscopyProject | None) -> AbsorptionLine | None:
        """Resolve the selected line id to a current line through `project`.

        A stored id whose line no longer exists resolves to ``None``: this is
        valid user-state absence, not an error.
        """
        if self.selected_line_id is None or project is None:
            return None
        return project.absorption_lines.get(self.selected_line_id)

    def reset_for_project_change(self) -> None:
        """Atomically clear selected line and fit display status.

        Required on project switch/close so neither half of the pair can
        survive into a new project on its own.
        """
        self.selected_line_id = None
        self.fit_status = FitReadyView()

    def clear_selection_outside_region(
        self, project: SpectroscopyProject | None, region_id: str | None
    ) -> bool:
        """Clear the selected line if it does not belong to `region_id`.

        Returns:
            Whether the selection was cleared.
        """
        if self.selected_line_id is None:
            return False
        line = self.resolve_selected_line(project)
        if line is None or line.region_id != region_id:
            self.selected_line_id = None
            return True
        return False

    def drop_vanished_selection(self, project: SpectroscopyProject | None) -> bool:
        """Clear the selected line if it no longer resolves from `project`.

        Returns:
            Whether the selection was cleared.
        """
        if self.selected_line_id is None:
            return False
        if self.resolve_selected_line(project) is None:
            self.selected_line_id = None
            return True
        return False
