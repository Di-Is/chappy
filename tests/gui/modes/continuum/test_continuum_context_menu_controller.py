"""Tests for continuum context menu controller."""

from __future__ import annotations

from chappy.gui.modes.continuum import ContinuumContextMenuController, ContinuumContextMenuRequest
from chappy.gui.protocols.context_menu import ContextMenuTriggerAction
from chappy.gui.protocols.intent_types import AddContinuumPointIntent, DeleteContinuumPointIntent


def test_actions_for_request_builds_add_point_intent() -> None:
    """The add action should carry a typed continuum add intent."""
    controller = ContinuumContextMenuController()

    actions = controller.actions_for_request(
        ContinuumContextMenuRequest(
            wavelength=1215.67, flux=0.8, can_add=True, can_delete=False, nearest_index=None
        )
    )

    add_action = actions[0]

    assert isinstance(add_action, ContextMenuTriggerAction)
    assert add_action.label == "Add Control Point"
    assert add_action.enabled is True
    assert isinstance(add_action.intent, AddContinuumPointIntent)
    assert add_action.intent.wavelength == 1215.67
    assert add_action.intent.flux == 0.8


def test_actions_for_request_disables_unavailable_delete_action() -> None:
    """The delete action should be disabled without a target point."""
    controller = ContinuumContextMenuController()

    actions = controller.actions_for_request(
        ContinuumContextMenuRequest(
            wavelength=1215.67, flux=0.8, can_add=True, can_delete=True, nearest_index=None
        )
    )

    delete_action = actions[1]

    assert isinstance(delete_action, ContextMenuTriggerAction)
    assert delete_action.label == "Delete Control Point"
    assert delete_action.enabled is False
    assert delete_action.intent is None


def test_actions_for_request_builds_delete_point_intent() -> None:
    """The delete action should carry a typed continuum delete intent."""
    controller = ContinuumContextMenuController()

    actions = controller.actions_for_request(
        ContinuumContextMenuRequest(
            wavelength=1215.67, flux=None, can_add=False, can_delete=True, nearest_index=3
        )
    )

    delete_action = actions[1]

    assert isinstance(delete_action, ContextMenuTriggerAction)
    assert delete_action.enabled is True
    assert isinstance(delete_action.intent, DeleteContinuumPointIntent)
    assert delete_action.intent.index == 3
