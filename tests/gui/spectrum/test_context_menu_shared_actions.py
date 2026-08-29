"""Tests for shared actions appended to the spectrum context menu."""

from __future__ import annotations

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from chappy.gui.protocols.context_menu import (
    ContextMenuActionDescriptor,
    ContextMenuActionIntent,
    ContextMenuTriggerAction,
)
from chappy.gui.protocols.intent_types import ShowContextMenuIntent, ToggleVelocityPlotIntent
from chappy.gui.spectrum import context_menu_controller
from chappy.gui.spectrum.context_menu_controller import SpectrumContextMenuController

INTENT = ShowContextMenuIntent(wavelength=1215.67, flux=0.5, global_x=10, global_y=20)


class _ExecutedMenu(QMenu):
    """Menu double that records its content instead of entering an event loop."""

    shown: list[_ExecutedMenu] = []

    def exec(self, *args: object, **kwargs: object) -> QAction | None:
        """Record the menu as shown without blocking on user input.

        Args:
            args: Ignored positional arguments from the production call.
            kwargs: Ignored keyword arguments from the production call.

        Returns:
            None, because no action is triggered.
        """
        del args, kwargs
        _ExecutedMenu.shown.append(self)
        return None


@pytest.fixture()
def menu_recorder(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> type[_ExecutedMenu]:
    """Replace themed menu creation with a non-blocking recording menu.

    Args:
        qapp: Qt application owning the created widgets.
        monkeypatch: Pytest monkeypatch helper.

    Returns:
        The recording menu type whose ``shown`` list holds displayed menus.
    """
    del qapp
    _ExecutedMenu.shown = []
    monkeypatch.setattr(
        context_menu_controller,
        "create_styled_menu",
        lambda parent=None, title="": _ExecutedMenu(parent),
    )
    return _ExecutedMenu


def _controller(
    descriptors: tuple[ContextMenuActionDescriptor, ...], view: QWidget
) -> SpectrumContextMenuController:
    """Build a controller returning fixed descriptors.

    Args:
        descriptors: Mode-provided descriptors for every menu request.
        view: Widget used as the menu parent.

    Returns:
        Controller under test.
    """
    return SpectrumContextMenuController(
        view_provider=lambda: view,
        action_provider=lambda _intent: descriptors,
        intent_handler=lambda _intent: None,
    )


def test_shared_actions_follow_mode_actions_after_a_separator(
    menu_recorder: type[_ExecutedMenu],
) -> None:
    """Shared display actions are appended below the mode-specific entries."""
    view = QWidget()
    shared_action = QAction("Component profiles", view)
    descriptor = ContextMenuTriggerAction(
        label="Show velocity", intent=ToggleVelocityPlotIntent(wavelength=1215.67)
    )
    controller = _controller((descriptor,), view)
    controller.set_shared_actions(lambda: (shared_action,))

    controller.show(INTENT)

    menu = menu_recorder.shown[-1]
    actions = menu.actions()
    assert [action.text() for action in actions[:1]] == ["Show velocity"]
    assert actions[1].isSeparator()
    assert actions[2] is shared_action


def test_menu_shows_shared_actions_without_mode_descriptors(
    menu_recorder: type[_ExecutedMenu],
) -> None:
    """A mode with no context actions still exposes the shared display toggles."""
    view = QWidget()
    shared_action = QAction("Error spectrum", view)
    controller = _controller((), view)
    controller.set_shared_actions(lambda: (shared_action,))

    controller.show(INTENT)

    menu = menu_recorder.shown[-1]
    assert menu.actions() == [shared_action]


def test_menu_stays_hidden_without_any_actions(menu_recorder: type[_ExecutedMenu]) -> None:
    """No descriptors and no shared actions must not open an empty menu."""
    view = QWidget()
    controller = _controller((), view)

    controller.show(INTENT)

    assert menu_recorder.shown == []


def test_intent_handler_receives_mode_descriptor_intents(
    menu_recorder: type[_ExecutedMenu],
) -> None:
    """Shared actions must not disturb mode intent delivery."""
    view = QWidget()
    handled: list[ContextMenuActionIntent] = []
    descriptor = ContextMenuTriggerAction(
        label="Show velocity", intent=ToggleVelocityPlotIntent(wavelength=1215.67)
    )
    controller = SpectrumContextMenuController(
        view_provider=lambda: view,
        action_provider=lambda _intent: (descriptor,),
        intent_handler=handled.append,
    )
    controller.set_shared_actions(lambda: (QAction("Error spectrum", view),))

    controller.show(INTENT)
    menu_recorder.shown[-1].actions()[0].trigger()

    assert handled == [descriptor.intent]
