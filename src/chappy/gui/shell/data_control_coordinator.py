"""Coordinate shared DataControlPanel workflows for the shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Slot

from chappy.gui.shell.data_control_panel import DataControlPanel, RangeValues

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.gui.spectrum.spectrum_view import SpectrumView


@dataclass(frozen=True, slots=True)
class DataControlCoordinatorPorts:
    """Typed collaborators consumed by DataControlCoordinator."""

    panel: DataControlPanel
    spectrum_view_provider: Callable[[], SpectrumView | None]
    status_message: Callable[[str, int], None]


class DataControlCoordinator(QObject):
    """Own shared DataControlPanel signal handling for the shell."""

    def __init__(self, ports: DataControlCoordinatorPorts, parent: QObject | None = None) -> None:
        """Initialize the coordinator.

        Args:
            ports: Typed collaborators used for routing shared data-control actions.
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._ports = ports

    def connect_signals(self) -> None:
        """Connect panel and spectrum callbacks to this coordinator."""
        panel = self._ports.panel
        panel.wavelength_range_applied.connect(self._apply_wavelength_range)
        panel.flux_range_applied.connect(self._apply_flux_range)
        panel.reset_requested.connect(self.reset_view)
        panel.auto_adjust_requested.connect(self.auto_adjust_flux)

        spectrum_view = self._ports.spectrum_view_provider()
        if spectrum_view is None:
            return

        spectrum_view.set_wavelength_fields_enabled_callback(self.set_wavelength_fields_enabled)
        spectrum_view.range_changed.connect(self._on_spectrum_range_changed)

    def set_wavelength_fields_enabled(self, enabled: bool) -> None:
        """Apply wavelength field availability to the shared data panel."""
        self._ports.panel.set_wavelength_fields_enabled(enabled)

    @Slot(float, float)
    def _apply_wavelength_range(self, min_wave: float, max_wave: float) -> None:
        """Apply a manual wavelength-range update."""
        spectrum_view = self._ports.spectrum_view_provider()
        if spectrum_view is None:
            return

        spectrum_view.coordinator.coordinate_range_update(
            source="manual", min_wave=min_wave, max_wave=max_wave
        )

    @Slot(float, float)
    def _apply_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Apply a manual flux-range update while preserving the wavelength range."""
        spectrum_view = self._ports.spectrum_view_provider()
        if spectrum_view is None:
            return

        min_wave, max_wave = spectrum_view.get_wavelength_range()
        spectrum_view.coordinator.coordinate_range_update(
            source="manual", min_wave=min_wave, max_wave=max_wave, flux_range=(min_flux, max_flux)
        )

    @Slot()
    def reset_view(self) -> None:
        """Reset the shared spectrum view to the stored default range."""
        spectrum_view = self._ports.spectrum_view_provider()
        if spectrum_view is None:
            return

        presenter = spectrum_view.coordinator
        reset_payload = spectrum_view.get_reset_ranges()
        if reset_payload is not None:
            wavelength_range, flux_range = reset_payload
            presenter.reset_view_ranges(wavelength_range=wavelength_range, flux_range=flux_range)
        else:
            presenter.reset_view_ranges()

        self._ports.status_message(self.tr("Reset plot ranges"), 1500)

    @Slot()
    def auto_adjust_flux(self) -> None:
        """Apply automatic flux scaling through the spectrum coordinator."""
        spectrum_view = self._ports.spectrum_view_provider()
        if spectrum_view is None:
            return

        spectrum_view.coordinator.handle_auto_flux_range_request()
        self._ports.status_message(self.tr("Auto-adjusted flux axis"), 1500)

    @Slot(float, float, float, float)
    def _on_spectrum_range_changed(
        self, min_wave: float, max_wave: float, min_flux: float, max_flux: float
    ) -> None:
        """Synchronize the shared panel with the latest displayed ranges."""
        self._ports.panel.update_ranges(
            RangeValues(
                wavelength_min=min_wave,
                wavelength_max=max_wave,
                flux_min=min_flux,
                flux_max=max_flux,
            )
        )


__all__ = ["DataControlCoordinator", "DataControlCoordinatorPorts"]
