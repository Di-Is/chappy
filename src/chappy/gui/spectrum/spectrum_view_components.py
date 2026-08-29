"""Typed component bundle for the spectrum view composition root."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chappy.gui.spectrum.interaction.input.ports import SpectrumInputFacadePort
    from chappy.gui.spectrum.range_input_controls import SpectrumRangeInputControls
    from chappy.gui.spectrum.spectrum_data_bridge import SpectrumDataBridge
    from chappy.gui.spectrum.spectrum_plot import SpectrumPlotHost


@dataclass(frozen=True, slots=True)
class SpectrumViewComponents:
    """Required components used by the spectrum interaction Facade."""

    data_bridge: SpectrumDataBridge
    plot_host: SpectrumPlotHost
    range_input_controls: SpectrumRangeInputControls
    interactor: SpectrumInputFacadePort


__all__ = ["SpectrumViewComponents"]
