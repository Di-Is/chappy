"""Tests for optimize context menu controller."""

from __future__ import annotations

from chappy.gui.modes.analysis.region_detail import (
    OptimizeContextMenuController,
    OptimizeContextMenuRequest,
)
from chappy.gui.protocols.context_menu import ContextMenuToggleAction, ContextMenuTriggerAction
from chappy.gui.protocols.intent_types import (
    AddOptimizeComponentIntent,
    ToggleOptimizeVelocityPlotIntent,
)


def test_actions_for_request_builds_add_component_intent() -> None:
    """The add action should carry a typed optimize add intent when allowed."""
    controller = OptimizeContextMenuController()

    actions = controller.actions_for_request(
        OptimizeContextMenuRequest(
            wavelength=1215.67,
            can_add_component=True,
            has_selected_line=True,
            has_selected_region=True,
            velocity_plot_visible=False,
        )
    )

    add_action = actions[0]

    assert isinstance(add_action, ContextMenuTriggerAction)
    assert add_action.label == "Add Component Here"
    assert add_action.enabled is True
    assert add_action.tooltip is None
    assert isinstance(add_action.intent, AddOptimizeComponentIntent)
    assert add_action.intent.wavelength == 1215.67


def test_actions_for_request_explains_add_component_rejection() -> None:
    """The add action should expose a tooltip when a selected line is out of range."""
    controller = OptimizeContextMenuController()

    actions = controller.actions_for_request(
        OptimizeContextMenuRequest(
            wavelength=1215.67,
            can_add_component=False,
            has_selected_line=True,
            has_selected_region=True,
            velocity_plot_visible=False,
        )
    )

    add_action = actions[0]

    assert isinstance(add_action, ContextMenuTriggerAction)
    assert add_action.enabled is False
    assert add_action.tooltip == "Out of selected line range"
    assert add_action.intent is None


def test_actions_for_request_builds_velocity_toggle_action() -> None:
    """The velocity action should carry typed optimize toggle intents."""
    controller = OptimizeContextMenuController()

    actions = controller.actions_for_request(
        OptimizeContextMenuRequest(
            wavelength=1215.67,
            can_add_component=True,
            has_selected_line=True,
            has_selected_region=True,
            velocity_plot_visible=True,
        )
    )

    velocity_action = actions[1]

    assert isinstance(velocity_action, ContextMenuToggleAction)
    assert velocity_action.label == "Show Velocity Plot (V)"
    assert velocity_action.enabled is True
    assert velocity_action.checked is True
    assert isinstance(velocity_action.intent_when_checked, ToggleOptimizeVelocityPlotIntent)
    assert isinstance(velocity_action.intent_when_unchecked, ToggleOptimizeVelocityPlotIntent)


def test_actions_for_request_explains_missing_region() -> None:
    """The velocity action should explain why it is disabled without a region."""
    controller = OptimizeContextMenuController()

    actions = controller.actions_for_request(
        OptimizeContextMenuRequest(
            wavelength=1215.67,
            can_add_component=False,
            has_selected_line=False,
            has_selected_region=False,
            velocity_plot_visible=False,
        )
    )

    velocity_action = actions[1]

    assert isinstance(velocity_action, ContextMenuToggleAction)
    assert velocity_action.enabled is False
    assert velocity_action.tooltip == "Please select a region"
