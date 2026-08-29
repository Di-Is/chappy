"""Plot adapter for continuum workflow rendering."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from chappy.core.components.continuum import ContinuumComponent
from chappy.core.editing_mode import EditingMode

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from chappy.core.spectroscopy_project import SpectroscopyProject

logger = logging.getLogger(__name__)
FloatArray = NDArray[np.float64]


class ContinuumSpectrumPlotPort(Protocol):
    """Spectrum plot endpoint required by continuum workflow rendering."""

    def enable_continuum_editing(self, enabled: bool) -> None:
        """Enable or disable continuum editing on the plot."""
        ...

    def ensure_continuum_reference_line(self) -> None:
        """Ensure the continuum reference line is visible."""
        ...

    def set_continuum_data(
        self,
        wavelength: FloatArray,
        continuum_flux: FloatArray,
        anchor_points: Sequence[tuple[float, float]],
    ) -> None:
        """Display continuum curve and anchor points."""
        ...

    def hide_continuum_display(self) -> None:
        """Hide the continuum display."""
        ...

    def update_continuum_preview(self, wavelength: FloatArray, preview_flux: FloatArray) -> None:
        """Display a transient continuum preview curve."""
        ...


class ContinuumViewStackPort(Protocol):
    """View-stack endpoint required by the continuum workflow."""

    spectrum_view: ContinuumSpectrumViewPort | None

    def get_all_views(self) -> Sequence[ViewWithPlot]:
        """Return views that may expose continuum visibility controls."""
        ...

    def get_spectrum_plot(self) -> ContinuumSpectrumPlotPort | None:
        """Return the spectrum plot endpoint."""
        ...


class ContinuumSnapshotSignal(Protocol):
    """Signal carrying continuum interaction snapshots."""

    def connect(self, slot: Callable[..., None], /) -> None:
        """Connect a continuum snapshot slot."""
        ...


class ContinuumPresenterPort(Protocol):
    """Presenter endpoint that emits interaction snapshots."""

    interaction_snapshot_applied: ContinuumSnapshotSignal


class ContinuumSpectrumViewPort(Protocol):
    """Spectrum view endpoint used to reach the interaction presenter."""

    coordinator: ContinuumPresenterPort


@runtime_checkable
class ViewWithPlot(Protocol):
    """View endpoint with continuum visibility controls."""

    def set_continuum_visibility(self, visible: bool) -> None:
        """Show or hide continuum elements in the view."""
        ...

    def update_continuum_display(self) -> None:
        """Refresh continuum rendering to reflect current state."""
        ...

    def ensure_continuum_reference_line(self) -> None:
        """Ensure a reference line exists for continuum interactions."""
        ...


@dataclass(frozen=True)
class ContinuumPlotAdapterPorts:
    """Ports required by the continuum plot adapter."""

    project_provider: Callable[[], SpectroscopyProject | None]
    view_stack_provider: Callable[[], ContinuumViewStackPort | None]
    table_refresh_callback: Callable[[], None]


class ContinuumPlotAdapter:
    """Update continuum visibility and plot data through typed plot ports."""

    def __init__(self, ports: ContinuumPlotAdapterPorts) -> None:
        """Initialize the adapter.

        Args:
            ports: Shell endpoints required to read project and update plot state.
        """
        self._ports = ports

    def update_visibility(self, mode: EditingMode) -> None:
        """Update continuum view visibility for the active mode."""
        view_stack = self._required_view_stack()

        continuum_visible = mode == EditingMode.CONTINUUM
        for view in view_stack.get_all_views():
            if isinstance(view, ViewWithPlot):
                view.set_continuum_visibility(continuum_visible)
                view.update_continuum_display()

        logger.debug("Updated continuum visualization for mode: %s", mode)

    def apply_mode_visualization(self, mode: EditingMode) -> None:
        """Apply continuum plot state for a mode transition."""
        view_stack = self._required_view_stack()
        spectrum_plot = self._required_spectrum_plot(view_stack)

        if mode != EditingMode.CONTINUUM:
            spectrum_plot.hide_continuum_display()
            spectrum_plot.enable_continuum_editing(False)
            logger.debug("Disabled continuum visualization for mode: %s", mode.value)
            return

        project = self._ports.project_provider()
        if project is None:
            return

        spectrum_plot.enable_continuum_editing(True)
        spectrum_plot.ensure_continuum_reference_line()

        continuum = self._first_continuum(project)
        observed = project.model.observed_spectrum
        if continuum is None or observed is None or continuum.num_continuum_points() <= 0:
            logger.debug("No continuum points to display in continuum mode")
            return

        self._set_continuum_data(spectrum_plot, continuum, observed.wavelength)

    def refresh_display(self, continuum: ContinuumComponent) -> None:
        """Refresh continuum curve, anchor points, and side-panel table."""
        project = self._ports.project_provider()
        if project is not None:
            view_stack = self._required_view_stack()
            spectrum_plot = self._required_spectrum_plot(view_stack)
            observed = project.model.observed_spectrum
            if observed is not None:
                anchor_points = continuum.get_continuum_points()
                if anchor_points:
                    self._set_continuum_data(spectrum_plot, continuum, observed.wavelength)
                else:
                    spectrum_plot.hide_continuum_display()

        self._ports.table_refresh_callback()

    def update_preview(self, wavelength: FloatArray, preview_flux: FloatArray) -> None:
        """Render a transient continuum preview curve."""
        view_stack = self._required_view_stack()
        spectrum_plot = self._required_spectrum_plot(view_stack)
        spectrum_plot.update_continuum_preview(wavelength, preview_flux)

    def _required_view_stack(self) -> ContinuumViewStackPort:
        """Return the required view stack or fail on missing composition."""
        view_stack = self._ports.view_stack_provider()
        if view_stack is None:
            msg = "Continuum plot adapter requires a view stack."
            raise RuntimeError(msg)
        return view_stack

    @staticmethod
    def _required_spectrum_plot(view_stack: ContinuumViewStackPort) -> ContinuumSpectrumPlotPort:
        """Return the required spectrum plot or fail on missing composition."""
        spectrum_plot = view_stack.get_spectrum_plot()
        if spectrum_plot is None:
            msg = "Continuum plot adapter requires a spectrum plot."
            raise RuntimeError(msg)
        return spectrum_plot

    @staticmethod
    def _first_continuum(project: SpectroscopyProject) -> ContinuumComponent | None:
        for component in project.model.components:
            if isinstance(component, ContinuumComponent):
                return component
        return None

    @staticmethod
    def _set_continuum_data(
        spectrum_plot: ContinuumSpectrumPlotPort,
        continuum: ContinuumComponent,
        wavelength: FloatArray,
    ) -> None:
        continuum_flux = continuum.calculate(wavelength)
        anchor_points = continuum.get_continuum_points()
        spectrum_plot.set_continuum_data(wavelength, continuum_flux, anchor_points)
        logger.debug("Updated continuum plot with %d anchor points", len(anchor_points))
