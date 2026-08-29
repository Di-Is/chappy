"""Optional range input controls for SpectrumView."""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from PySide6.QtWidgets import QDoubleSpinBox

    from chappy.gui.spectrum.spectrum_view import SpectrumView


class SpectrumRangeInputControls(QObject):
    """Adapter for optional range input widgets.

    The current spectrum range is owned by SpectrumDataBridge via RangeCoordinator.
    This adapter only mirrors coordinated range updates into connected input widgets
    and emits user-entered wavelength changes when such widgets exist.

    Signals:
        wavelength_range_changed: Emitted when a connected wavelength input changes.
    """

    wavelength_range_changed = Signal(float, float)

    def __init__(self, parent_view: "SpectrumView") -> None:
        """Initialize the optional range input adapter.

        Args:
            parent_view: Parent SpectrumView instance.
        """
        super().__init__()
        self.parent_view = parent_view

        self.min_wave_spin: QDoubleSpinBox | None = None
        self.max_wave_spin: QDoubleSpinBox | None = None
        self.min_flux_spin: QDoubleSpinBox | None = None
        self.max_flux_spin: QDoubleSpinBox | None = None

    def set_wavelength_range(self, min_wave: float, max_wave: float) -> None:
        """Mirror a wavelength range into connected input widgets.

        Args:
            min_wave: Minimum wavelength.
            max_wave: Maximum wavelength.
        """
        if not self.min_wave_spin or not self.max_wave_spin:
            return

        self.min_wave_spin.setValue(min_wave)
        self.max_wave_spin.setValue(max_wave)

    def set_flux_range(self, min_flux: float, max_flux: float) -> None:
        """Mirror a flux range into connected input widgets.

        Args:
            min_flux: Minimum flux.
            max_flux: Maximum flux.
        """
        if not self.min_flux_spin or not self.max_flux_spin:
            return

        self.min_flux_spin.setValue(min_flux)
        self.max_flux_spin.setValue(max_flux)
