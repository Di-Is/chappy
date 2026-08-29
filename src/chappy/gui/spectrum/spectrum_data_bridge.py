"""Data bridge and business logic for spectrum view.

This module handles project data, spectrum data operations,
and selection state management.
"""

from __future__ import annotations

import contextlib
import logging
from math import isfinite
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.adapters.model_event_adapter import SpectrumModelEventAdapter

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

type SpectrumArrayTriple = tuple[
    "NDArray[np.float64]", "NDArray[np.float64]", "NDArray[np.float64] | None"
]
type SpectrumArrayPair = tuple["NDArray[np.float64]", "NDArray[np.float64]"]


class SpectrumDataBridge(QObject):
    """Bridges spectrum data and business logic to the GUI.

    Responsibilities:
    - Project data management
    - Spectrum data operations
    - Selection state management
    - Data change notifications
    """

    # Signals
    project_changed = Signal(SpectroscopyProject)
    data_updated = Signal()
    selection_changed = Signal(str)  # selected item id
    range_changed = Signal(float, float, float, float)  # min/max wavelength/flux

    def __init__(self) -> None:
        """Initialize the data bridge."""
        super().__init__()

        # Core data
        self._project: SpectroscopyProject | None = None
        self._model_event_adapter: SpectrumModelEventAdapter | None = None

        # Display ranges
        self._wavelength_range: tuple[float, float] | None = None
        self._flux_range: tuple[float, float] | None = None

        # State flags
        self._updating = False

    @property
    def project(self) -> SpectroscopyProject | None:
        """Get current project."""
        return self._project

    def set_project(self, project: SpectroscopyProject | None) -> None:
        """Set the current project.

        Args:
            project: Project to set, or None to clear
        """
        if self._project == project:
            return

        old_project = self._project
        self._project = project

        if self._model_event_adapter is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                self._model_event_adapter.model_changed.disconnect(self._on_model_changed)
            self._model_event_adapter.close()
            self._model_event_adapter = None

        # Connect new project signals
        if project and project.model:
            self._model_event_adapter = SpectrumModelEventAdapter(project.model, self)
            self._model_event_adapter.model_changed.connect(self._on_model_changed)

            if not project.model.is_model_valid:
                project.model.rebuild_model_storage()

        # Emit change signal
        self.project_changed.emit(project)

        logger.debug(
            "Project changed from %s to %s",
            old_project.name if old_project else "None",
            project.name if project else "None",
        )

    def get_spectrum_data(self) -> SpectrumArrayTriple | None:
        """Get current spectrum data.

        Returns:
            Tuple of (wavelength, flux, error) arrays or None
        """
        if not self._project or not self._project.model.observed_spectrum:
            return None

        spectrum = self._project.model.observed_spectrum
        return spectrum.wavelength, spectrum.flux, spectrum.error

    def get_model_data(self) -> SpectrumArrayPair | None:
        """Get current model data.

        Returns:
            Tuple of (wavelength, model_flux) arrays or None
        """
        if not self._project or not self._project.model.model_spectrum:
            return None

        model = self._project.model.model_spectrum
        return model.wavelength, model.flux

    # ========== Range Management ==========

    def set_wavelength_range(self, min_wave: float, max_wave: float) -> None:
        """Set wavelength display range.

        Args:
            min_wave: Minimum wavelength
            max_wave: Maximum wavelength
        """
        if self._updating:
            return

        self._updating = True
        try:
            self._wavelength_range = (min_wave, max_wave)

            # Emit range changed with current flux range
            flux_min, flux_max = self.get_flux_range()
            self.range_changed.emit(min_wave, max_wave, flux_min, flux_max)

        finally:
            self._updating = False

        logger.debug("Wavelength range set: %.2f - %.2f", min_wave, max_wave)

    def get_wavelength_range(self) -> tuple[float, float]:
        """Get current wavelength range.

        Returns:
            Tuple of (min_wavelength, max_wavelength)
        """
        if self._wavelength_range:
            return self._wavelength_range

        # Calculate from data if not set
        data = self.get_spectrum_data()
        if data:
            wavelength = data[0]
            return self._array_range(wavelength, "wavelength")

        msg = "Wavelength range is required but no spectrum data is loaded."
        raise RuntimeError(msg)

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Set flux display range.

        Args:
            min_flux: Minimum flux
            max_flux: Maximum flux
        """
        if self._updating:
            return

        self._updating = True
        try:
            self._flux_range = (min_flux, max_flux)

            # Emit range changed with current wavelength range
            wave_min, wave_max = self.get_wavelength_range()
            self.range_changed.emit(wave_min, wave_max, min_flux, max_flux)

        finally:
            self._updating = False

        logger.debug("Flux range set: %.2f - %.2f", min_flux, max_flux)

    def get_flux_range(self) -> tuple[float, float]:
        """Get current flux range.

        Returns:
            Tuple of (min_flux, max_flux)
        """
        if self._flux_range:
            return self._flux_range

        # Calculate from data if not set
        data = self.get_spectrum_data()
        if data:
            flux = data[1]
            return self._array_range(flux, "flux")

        msg = "Flux range is required but no spectrum data is loaded."
        raise RuntimeError(msg)

    def auto_scale_ranges(self) -> None:
        """Automatically scale ranges to fit data.

        Note:
            This method sets the raw data ranges without any display margins.
            Display margins are handled by the Renderer layer (View) for proper
            separation of concerns in the MVP-Lite pattern.
        """
        data = self.get_spectrum_data()
        if not data:
            return

        wavelength, flux, _ = data

        # Set wavelength range (raw data range, no margin)
        min_wave, max_wave = self._array_range(wavelength, "wavelength")
        self.set_wavelength_range(min_wave, max_wave)

        # Set flux range (raw data range, no margin)
        flux_min, flux_max = self._array_range(flux, "flux")
        self.set_flux_range(flux_min, flux_max)

    def _on_model_changed(self) -> None:
        """Handle model change events."""
        if self._updating:
            return

        self.data_updated.emit()
        logger.debug("Model data updated")

    @staticmethod
    def _array_range(array: NDArray[np.float64], label: str) -> tuple[float, float]:
        """Return finite range bounds for a required spectrum array."""
        if array.size == 0:
            msg = f"{label.capitalize()} data is required but empty."
            raise RuntimeError(msg)

        minimum = float(array.min())
        maximum = float(array.max())
        if not isfinite(minimum) or not isfinite(maximum):
            msg = f"{label.capitalize()} range contains non-finite bounds."
            raise RuntimeError(msg)

        return minimum, maximum
