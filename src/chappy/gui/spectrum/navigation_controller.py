"""Navigation intent controller for the spectrum surface."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from chappy.application.spectrum import (
    CenterOnWavelengthNavigationIntent,
    PanNavigationIntent,
    RangeNavigationIntent,
    RangeNavigationRequest,
    SelectRangeNavigationIntent,
    SpectrumRangeSource,
    ZoomFactorNavigationIntent,
    ZoomRectNavigationIntent,
)
from chappy.gui.protocols.intent_types import (
    CenterOnWavelengthIntent,
    PanIntent,
    SelectRangeIntent,
    ZoomFactorIntent,
    ZoomRectIntent,
)
from chappy.presentation.interaction.interaction_contracts import InteractionChannel

if TYPE_CHECKING:
    from collections.abc import Callable

    from chappy.application.spectrum.range_usecase import RangeNavigationUseCase

logger = logging.getLogger(__name__)

type SpectrumNavigationIntent = (
    PanIntent | ZoomFactorIntent | ZoomRectIntent | SelectRangeIntent | CenterOnWavelengthIntent
)


class CoordinateRangeUpdatePort(Protocol):
    """Callable port for coordinated range updates."""

    def __call__(
        self,
        source: str,
        min_wave: float,
        max_wave: float,
        *,
        flux_range: tuple[float, float] | None = None,
    ) -> None:
        """Apply a coordinated spectrum range update."""
        ...


@dataclass(frozen=True, slots=True)
class SpectrumNavigationControllerFactory:
    """Factory that builds navigation controllers with an explicit use case."""

    range_usecase: RangeNavigationUseCase

    def create(
        self,
        *,
        current_range_provider: Callable[[], tuple[float, float] | None],
        data_bounds_provider: Callable[[], tuple[float, float] | None],
        coordinate_range_update: CoordinateRangeUpdatePort,
        disable_auto_adjust_y: Callable[[], None],
        active_interaction_channel_provider: Callable[[], InteractionChannel | None],
        mode_command_emitter: Callable[[str], None],
    ) -> SpectrumNavigationController:
        """Create a navigation controller wired to spectrum-surface ports."""
        return SpectrumNavigationController(
            current_range_provider=current_range_provider,
            data_bounds_provider=data_bounds_provider,
            coordinate_range_update=coordinate_range_update,
            disable_auto_adjust_y=disable_auto_adjust_y,
            active_interaction_channel_provider=active_interaction_channel_provider,
            mode_command_emitter=mode_command_emitter,
            range_usecase=self.range_usecase,
        )


class SpectrumNavigationController:
    """Translate GUI navigation intents into coordinated range updates."""

    def __init__(
        self,
        *,
        current_range_provider: Callable[[], tuple[float, float] | None],
        data_bounds_provider: Callable[[], tuple[float, float] | None],
        coordinate_range_update: CoordinateRangeUpdatePort,
        disable_auto_adjust_y: Callable[[], None],
        active_interaction_channel_provider: Callable[[], InteractionChannel | None],
        mode_command_emitter: Callable[[str], None],
        range_usecase: RangeNavigationUseCase,
    ) -> None:
        """Initialize the navigation controller.

        Args:
            current_range_provider: Provider for the current visible wavelength range, or
                None when navigation is pending because no spectrum is loaded.
            data_bounds_provider: Provider for observed-spectrum wavelength bounds.
            coordinate_range_update: Port applying coordinated range updates.
            disable_auto_adjust_y: Port disabling automatic Y-axis adjustment.
            active_interaction_channel_provider: Provider for active interaction channel.
            mode_command_emitter: Port for mode command notifications.
            range_usecase: Required range navigation use case.
        """
        self._current_range_provider = current_range_provider
        self._data_bounds_provider = data_bounds_provider
        self._coordinate_range_update = coordinate_range_update
        self._disable_auto_adjust_y = disable_auto_adjust_y
        self._active_interaction_channel_provider = active_interaction_channel_provider
        self._mode_command_emitter = mode_command_emitter
        self._range_usecase = range_usecase

    def handle_navigation_intent(self, intent: SpectrumNavigationIntent) -> None:
        """Handle a spectrum navigation intent."""
        current_range = self._current_range_provider()
        if current_range is None:
            logger.debug("Ignoring navigation intent before spectrum data is loaded.")
            return
        navigation_intent = self._to_range_navigation_intent(intent)
        if navigation_intent is None:
            logger.debug("Ignoring unsupported navigation intent: %s", type(intent).__name__)
            return

        result = self._range_usecase.calculate(
            RangeNavigationRequest(
                current_range=current_range,
                intent=navigation_intent,
                data_bounds=self._data_bounds_provider(),
            )
        )
        new_range = result.wavelength_range

        if result.source is SpectrumRangeSource.RECT_ZOOM:
            logger.info(
                "ZoomRectIntent received - flux range: %s to %s",
                result.flux_range[0] if result.flux_range is not None else None,
                result.flux_range[1] if result.flux_range is not None else None,
            )
            self._disable_auto_adjust_y()
            self._coordinate_range_update(
                result.source.value, new_range[0], new_range[1], flux_range=result.flux_range
            )
            self._request_rect_zoom_teardown()
            return

        self._coordinate_range_update(result.source.value, new_range[0], new_range[1])

    def _to_range_navigation_intent(
        self, intent: SpectrumNavigationIntent
    ) -> RangeNavigationIntent | None:
        """Convert a GUI navigation intent into an application navigation intent."""
        if isinstance(intent, PanIntent):
            return PanNavigationIntent(fraction=float(intent.fraction))

        if isinstance(intent, ZoomFactorIntent):
            return ZoomFactorNavigationIntent(
                factor=float(intent.factor),
                center_wavelength=(
                    float(intent.center_wavelength)
                    if intent.center_wavelength is not None
                    else None
                ),
                cursor_relative_position=(
                    float(intent.cursor_relative_position)
                    if intent.cursor_relative_position is not None
                    else None
                ),
            )

        if isinstance(intent, ZoomRectIntent):
            return ZoomRectNavigationIntent(
                min_wavelength=float(intent.min_wavelength),
                max_wavelength=float(intent.max_wavelength),
                min_flux=float(intent.min_flux) if intent.min_flux is not None else None,
                max_flux=float(intent.max_flux) if intent.max_flux is not None else None,
            )

        if isinstance(intent, SelectRangeIntent):
            return SelectRangeNavigationIntent(
                start_wavelength=float(intent.start_wavelength),
                end_wavelength=float(intent.end_wavelength),
            )

        if isinstance(intent, CenterOnWavelengthIntent):
            return CenterOnWavelengthNavigationIntent(wavelength=float(intent.wavelength))

        return None

    def _request_rect_zoom_teardown(self) -> None:
        """Request that rectangle zoom mode is cleared after use."""
        if self._active_interaction_channel_provider() is not InteractionChannel.RECT_ZOOM:
            return

        logger.debug("Requesting rectangle zoom mode disable after zoom intent")
        self._mode_command_emitter("disable_rect_zoom")
