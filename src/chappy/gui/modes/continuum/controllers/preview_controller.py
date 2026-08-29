"""Preview controller for continuum point movement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chappy.core.components.continuum import ContinuumComponent

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.core.spectroscopy_project import SpectroscopyProject
    from chappy.gui.modes.continuum.plot_adapter import FloatArray


@dataclass(frozen=True)
class ContinuumPreviewPorts:
    """Ports required to calculate and render continuum previews."""

    project_provider: Callable[[], SpectroscopyProject | None]
    preview_display_callback: Callable[[FloatArray, FloatArray], None]


class ContinuumPreviewController:
    """Calculate continuum preview curves for in-progress point moves."""

    def __init__(self, ports: ContinuumPreviewPorts) -> None:
        """Initialize the controller.

        Args:
            ports: Project and display callbacks required for preview rendering.
        """
        self._ports = ports

    def update_preview(
        self,
        continuum: ContinuumComponent,
        point_index: int,
        current_position: tuple[float, float],
    ) -> None:
        """Calculate and render a transient continuum curve.

        Args:
            continuum: Continuum component being edited.
            point_index: Anchor point index being moved.
            current_position: Temporary point position.
        """
        project = self._ports.project_provider()
        if project is None or project.model.observed_spectrum is None:
            return

        preview_points = continuum.get_continuum_points()
        if not 0 <= point_index < len(preview_points):
            return

        wavelength = project.model.observed_spectrum.wavelength
        preview_points[point_index] = current_position
        preview_flux = ContinuumComponent.calculate_from_points(preview_points, wavelength)
        self._ports.preview_display_callback(wavelength, preview_flux)
