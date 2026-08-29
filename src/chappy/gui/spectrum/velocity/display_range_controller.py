"""Controller for the plot-local optimize velocity display-range session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chappy.presentation.velocity import (
    VelocityDisplayHalfWidth,
    VelocityDisplayRangeState,
    VelocityDisplayScopeKey,
    clear,
    commit_manual,
    fit_view_to_analysis_ranges,
    initialize,
    switch_scope,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


class VelocityDisplayRangeController:
    """Own one mode-independent velocity-overlay display-range session."""

    def __init__(
        self,
        *,
        apply_display_half_width: Callable[[VelocityDisplayHalfWidth], None],
        state_changed: Callable[[VelocityDisplayRangeState | None], None],
    ) -> None:
        """Store callbacks for the shared overlay widget and grid."""
        self._apply_display_half_width = apply_display_half_width
        self._state_changed = state_changed
        self._state: VelocityDisplayRangeState | None = None
        self._analysis_half_widths: tuple[float, ...] = ()

    @property
    def state(self) -> VelocityDisplayRangeState | None:
        """Return the current overlay-session state."""
        return self._state

    def activate(
        self, scope_key: VelocityDisplayScopeKey, analysis_half_widths: Iterable[float]
    ) -> None:
        """Open or refresh an overlay without overwriting its current display value."""
        widths = tuple(analysis_half_widths)
        if not widths:
            msg = "Velocity display requires analysis half-widths."
            raise ValueError(msg)

        if self._state is None:
            state = initialize(scope_key, widths)
        else:
            state = switch_scope(self._state, scope_key, widths)
        self._analysis_half_widths = widths
        self._publish(state)

    def commit_manual(self, value: VelocityDisplayHalfWidth) -> None:
        """Commit a validated user value without touching scientific state."""
        if self._state is None:
            msg = "Velocity display range session is not active."
            raise RuntimeError(msg)
        self._publish(commit_manual(self._state, value))

    def fit_view_to_analysis_ranges(self) -> None:
        """Explicitly derive the current scope's display range from analysis ranges."""
        if self._state is None:
            msg = "Velocity display range session is not active."
            raise RuntimeError(msg)
        self._publish(
            fit_view_to_analysis_ranges(self._state.scope_key, self._analysis_half_widths)
        )

    def clear(self) -> None:
        """Discard the overlay-local state on close, project switch, or mode exit."""
        clear()
        self._state = None
        self._analysis_half_widths = ()
        self._state_changed(None)

    def _publish(self, state: VelocityDisplayRangeState) -> None:
        """Apply one accepted state consistently to the control and all subplots."""
        self._state = state
        self._apply_display_half_width(state.value)
        self._state_changed(state)


__all__ = ["VelocityDisplayRangeController"]
