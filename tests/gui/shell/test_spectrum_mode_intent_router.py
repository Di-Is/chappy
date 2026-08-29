"""Tests for shell-owned spectrum mode intent routing."""

from __future__ import annotations

import pytest

from chappy.gui.protocols.context_menu import ContextMenuTriggerAction
from chappy.gui.protocols.intent_types import AddContinuumPointIntent, ShowContextMenuIntent
from chappy.gui.shell.spectrum_mode_intent_router import (
    SpectrumModeIntentRouter,
    SpectrumModeIntentRouterPorts,
)


class _Runtime:
    """Record routed shared-spectrum requests."""

    def __init__(self) -> None:
        """Initialize the runtime double."""
        self.clicks: list[tuple[float, float, int]] = []
        self.velocity_shortcut_count = 0
        self.context_menu_intents: list[object] = []
        self.context_menu_requests: list[ShowContextMenuIntent] = []

    def handle_mode_click(self, wavelength: float, flux: float, modifiers: int) -> None:
        """Record a routed spectrum click."""
        self.clicks.append((wavelength, flux, modifiers))

    def handle_mode_velocity_shortcut(self) -> None:
        """Record a routed velocity shortcut."""
        self.velocity_shortcut_count += 1

    def handle_context_menu_intent(self, intent: object) -> None:
        """Record a routed context-menu intent."""
        self.context_menu_intents.append(intent)

    def context_menu_actions(
        self, request: ShowContextMenuIntent
    ) -> tuple[ContextMenuTriggerAction, ...]:
        """Return a runtime-local context-menu action list."""
        self.context_menu_requests.append(request)
        return (ContextMenuTriggerAction(label="Action", intent=None),)


class _RouterState:
    """Mutable state used by router tests."""

    def __init__(self) -> None:
        """Initialize router state."""
        self.active_runtime: _Runtime | None = None

    def create_router(self) -> SpectrumModeIntentRouter:
        """Create a router backed by this state."""
        return SpectrumModeIntentRouter(
            SpectrumModeIntentRouterPorts(active_runtime_provider=lambda: self.active_runtime)
        )


def test_mode_click_routes_to_active_runtime() -> None:
    """Shared spectrum clicks should route to the active runtime."""
    state = _RouterState()
    state.active_runtime = _Runtime()
    router = state.create_router()

    router.handle_mode_click(1215.67, 0.8, 4)

    assert state.active_runtime.clicks == [(1215.67, 0.8, 4)]


def test_velocity_shortcut_routes_to_active_runtime() -> None:
    """Velocity shortcuts should route to the active runtime."""
    state = _RouterState()
    state.active_runtime = _Runtime()
    router = state.create_router()

    router.handle_mode_velocity_shortcut()

    assert state.active_runtime.velocity_shortcut_count == 1


def test_context_menu_intent_routes_to_active_runtime() -> None:
    """Context-menu intents should route to the active runtime."""
    state = _RouterState()
    state.active_runtime = _Runtime()
    router = state.create_router()
    intent = AddContinuumPointIntent(wavelength=1215.67, flux=0.8)

    router.handle_context_menu_intent(intent)

    assert state.active_runtime.context_menu_intents == [intent]


def test_context_menu_actions_route_to_active_runtime() -> None:
    """Context-menu action discovery should use the active runtime only."""
    state = _RouterState()
    state.active_runtime = _Runtime()
    router = state.create_router()
    request = ShowContextMenuIntent(wavelength=1215.67, flux=0.8, global_x=10, global_y=20)

    actions = router.context_menu_actions(request)

    assert actions == (ContextMenuTriggerAction(label="Action", intent=None),)
    assert state.active_runtime.context_menu_requests == [request]


def test_context_menu_intent_requires_active_runtime() -> None:
    """Selected context-menu intents should fail fast without an active runtime."""
    router = _RouterState().create_router()

    with pytest.raises(RuntimeError, match="Active mode runtime is required"):
        router.handle_context_menu_intent(AddContinuumPointIntent(wavelength=1215.67, flux=0.8))


def test_no_active_runtime_yields_empty_context_menu_actions() -> None:
    """Action discovery should be empty when no runtime is active."""
    router = _RouterState().create_router()

    actions = router.context_menu_actions(
        ShowContextMenuIntent(wavelength=1215.67, flux=0.8, global_x=10, global_y=20)
    )

    assert actions == ()
