"""Modal-dialog spotlight tests for the guided tutorial."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

from chappy.core.editing_mode import EditingMode
from chappy.gui.common.tutorial import (
    AdvanceTrigger,
    TutorialChapter,
    TutorialCompletion,
    TutorialDestination,
    TutorialStep,
    TutorialTarget,
    TutorialTargetProminence,
    TutorialTargetRole,
)
from chappy.gui.shell.tutorial_tour_controller import TutorialTourController

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest
    from pytestqt.qtbot import QtBot

_DIALOG_BUTTON_NAME = "presetNewButton"


def _target(
    object_name: str, prominence: TutorialTargetProminence = TutorialTargetProminence.PRIMARY
) -> TutorialTarget:
    return TutorialTarget(
        object_name=object_name, role=TutorialTargetRole.INTERACT, prominence=prominence
    )


def _chapter(*targets: TutorialTarget) -> TutorialChapter:
    return TutorialChapter(
        chapter_id="modal",
        title_source="Modal",
        destination=TutorialDestination(mode=EditingMode.IDENTIFY),
        steps=(
            TutorialStep(
                targets=targets,
                action_source="Interact with the dialog",
                expected_source="The dialog target is highlighted",
            ),
        ),
    )


def _controller(
    host: QWidget,
    chapter: TutorialChapter,
    *,
    completion_checks: dict[TutorialCompletion, Callable[[], bool]] | None = None,
) -> TutorialTourController:
    return TutorialTourController(
        host,
        chapters=(chapter,),
        switch_mode=lambda _mode: None,
        switch_analysis_surface=lambda _surface: True,
        switch_analysis_panel=lambda _panel: True,
        completion_checks=completion_checks,
    )


def _shown_host(qtbot: QtBot) -> QWidget:
    host = QWidget()
    host.resize(600, 400)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    return host


def _modal_dialog(host: QWidget) -> tuple[QDialog, QPushButton]:
    dialog = QDialog(host)
    dialog.resize(320, 200)
    dialog.setModal(True)
    button = QPushButton("New", dialog)
    button.setObjectName(_DIALOG_BUTTON_NAME)
    button.setGeometry(40, 40, 120, 40)
    return dialog, button


def _wait_for_overlay_window(
    qtbot: QtBot, controller: TutorialTourController, window: QWidget
) -> None:
    qtbot.waitUntil(
        lambda: controller._overlay is not None and controller._overlay.window() is window
    )


def test_dialog_target_spotlights_on_dialog_window(qtbot: QtBot) -> None:
    """Opening a modal dialog must move overlay and bubble onto the dialog."""
    host = _shown_host(qtbot)
    controller = _controller(host, _chapter(_target(_DIALOG_BUTTON_NAME)))
    controller.start()
    assert controller._overlay is not None
    assert controller._overlay.window() is host
    assert controller._overlay.spotlight_rects() == ()

    dialog, button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)

    _wait_for_overlay_window(qtbot, controller, dialog)
    assert controller._bubble is not None
    assert controller._bubble.window() is dialog
    primary = controller._overlay.primary_spotlight_rect()
    assert primary is not None
    assert primary.contains(button.mapTo(dialog, button.rect().center()))
    controller.stop()


def test_closing_dialog_returns_widgets_to_main_window(qtbot: QtBot) -> None:
    """Rejecting the dialog must rebuild the overlay on the main window."""
    host = _shown_host(qtbot)
    controller = _controller(host, _chapter(_target(_DIALOG_BUTTON_NAME)))
    controller.start()
    dialog, _button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)
    _wait_for_overlay_window(qtbot, controller, dialog)

    dialog.reject()

    _wait_for_overlay_window(qtbot, controller, host)
    assert controller._bubble is not None
    assert controller._bubble.window() is host
    assert controller._overlay is not None
    assert controller._overlay.spotlight_rects() == ()
    assert controller.is_active
    controller.stop()


def test_accept_and_reopen_restores_dialog_spotlight(qtbot: QtBot) -> None:
    """Accept then reopen must spotlight the dialog target again."""
    host = _shown_host(qtbot)
    controller = _controller(host, _chapter(_target(_DIALOG_BUTTON_NAME)))
    controller.start()
    dialog, _button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)
    _wait_for_overlay_window(qtbot, controller, dialog)

    dialog.accept()
    _wait_for_overlay_window(qtbot, controller, host)

    dialog.show()
    qtbot.waitExposed(dialog)
    _wait_for_overlay_window(qtbot, controller, dialog)
    assert controller._overlay is not None
    assert controller._overlay.primary_spotlight_rect() is not None
    controller.stop()


def test_deleting_closed_dialog_leaves_main_window_widgets_valid(qtbot: QtBot) -> None:
    """Destroying the dialog after close must not invalidate the tour widgets."""
    host = _shown_host(qtbot)
    controller = _controller(host, _chapter(_target(_DIALOG_BUTTON_NAME)))
    controller.start()
    dialog, _button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)
    _wait_for_overlay_window(qtbot, controller, dialog)

    dialog.reject()
    dialog.deleteLater()
    QApplication.processEvents()

    _wait_for_overlay_window(qtbot, controller, host)
    assert controller.is_active
    controller.stop()


def test_stop_while_dialog_open_removes_widgets_and_event_filter(qtbot: QtBot) -> None:
    """Stopping mid-dialog must destroy tour widgets and stay inert afterwards."""
    host = _shown_host(qtbot)
    controller = _controller(host, _chapter(_target(_DIALOG_BUTTON_NAME)))
    controller.start()
    dialog, _button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)
    _wait_for_overlay_window(qtbot, controller, dialog)

    controller.stop()

    assert controller._overlay is None
    assert controller._bubble is None
    dialog.hide()
    dialog.show()
    qtbot.wait(20)
    assert controller._overlay is None
    assert controller._bubble is None
    assert not controller.is_active


def test_targets_spanning_windows_prefer_main_window(
    qtbot: QtBot, caplog: pytest.LogCaptureFixture
) -> None:
    """A step spanning main window and dialog keeps only main-window targets."""
    host = _shown_host(qtbot)
    main_button = QPushButton("Main", host)
    main_button.setObjectName("mainTarget")
    main_button.setGeometry(30, 30, 100, 40)
    main_button.show()
    chapter = _chapter(
        _target("mainTarget"), _target(_DIALOG_BUTTON_NAME, TutorialTargetProminence.RELATED)
    )
    controller = _controller(host, chapter)
    controller.start()
    dialog, _button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)

    with caplog.at_level(logging.WARNING, logger="chappy.gui.shell.tutorial_tour_controller"):
        qtbot.waitUntil(
            lambda: any("span multiple windows" in record.message for record in caplog.records)
        )

    assert controller._overlay is not None
    assert controller._overlay.window() is host
    assert len(controller._overlay.spotlight_rects()) == 1
    controller.stop()


def _dialog_transition_chapter(main_button_name: str, dialog_name: str) -> TutorialChapter:
    return TutorialChapter(
        chapter_id="dialog_transition",
        title_source="Dialog transition",
        destination=TutorialDestination(mode=EditingMode.IDENTIFY),
        steps=(
            TutorialStep(
                targets=(_target(main_button_name),),
                action_source="Open the dialog",
                expected_source="The dialog opens",
                advance=AdvanceTrigger.DIALOG_SHOWN,
                advance_dialog=dialog_name,
            ),
            TutorialStep(
                targets=(_target(_DIALOG_BUTTON_NAME),),
                action_source="Interact with the dialog",
                expected_source="The dialog target is highlighted",
            ),
            TutorialStep(
                targets=(_target(_DIALOG_BUTTON_NAME),),
                action_source="Close the dialog",
                expected_source="The dialog closes",
                advance=AdvanceTrigger.DIALOG_HIDDEN,
                advance_dialog=dialog_name,
            ),
            TutorialStep(
                targets=(),
                action_source="Back on the main window",
                expected_source="The tour continues",
            ),
        ),
    )


def test_dialog_show_advances_the_dialog_shown_step_onto_dialog_targets(qtbot: QtBot) -> None:
    """Opening the named dialog must advance past the open-instruction step."""
    host = _shown_host(qtbot)
    open_button = QPushButton("Open", host)
    open_button.setObjectName("mainOpenButton")
    open_button.setGeometry(30, 30, 100, 40)
    open_button.show()
    controller = _controller(host, _dialog_transition_chapter("mainOpenButton", "probeDialog"))
    controller.start()
    assert controller._step_index == 0
    assert controller._overlay is not None
    assert len(controller._overlay.spotlight_rects()) == 1

    dialog, button = _modal_dialog(host)
    dialog.setObjectName("probeDialog")
    dialog.show()
    qtbot.waitExposed(dialog)

    qtbot.waitUntil(lambda: controller._step_index == 1)
    _wait_for_overlay_window(qtbot, controller, dialog)
    assert controller._overlay is not None
    primary = controller._overlay.primary_spotlight_rect()
    assert primary is not None
    assert primary.contains(button.mapTo(dialog, button.rect().center()))
    controller.stop()


def test_dialog_hide_advances_the_dialog_hidden_step_back_to_main(qtbot: QtBot) -> None:
    """Closing the named dialog must advance past the close-instruction step."""
    host = _shown_host(qtbot)
    controller = _controller(host, _dialog_transition_chapter("mainOpenButton", "probeDialog"))
    controller.start()
    dialog, _button = _modal_dialog(host)
    dialog.setObjectName("probeDialog")
    dialog.show()
    qtbot.waitExposed(dialog)
    qtbot.waitUntil(lambda: controller._step_index == 1)
    controller._advance()
    assert controller._step_index == 2

    dialog.reject()

    qtbot.waitUntil(lambda: controller._step_index == 3)
    _wait_for_overlay_window(qtbot, controller, host)
    assert controller.is_active
    controller.stop()


def test_unrelated_dialog_show_does_not_advance_a_dialog_shown_step(qtbot: QtBot) -> None:
    """Only the dialog named by the step may drive the transition."""
    host = _shown_host(qtbot)
    open_button = QPushButton("Open", host)
    open_button.setObjectName("mainOpenButton")
    open_button.setGeometry(30, 30, 100, 40)
    open_button.show()
    controller = _controller(host, _dialog_transition_chapter("mainOpenButton", "probeDialog"))
    controller.start()

    other, _button = _modal_dialog(host)
    other.setObjectName("someOtherDialog")
    other.show()
    qtbot.waitExposed(other)
    qtbot.wait(20)

    assert controller._step_index == 0
    controller.stop()


def test_main_window_widget_wins_over_dialog_with_same_object_name(qtbot: QtBot) -> None:
    """Resolution must keep preferring the main window when names collide."""
    host = _shown_host(qtbot)
    main_button = QPushButton("Main", host)
    main_button.setObjectName(_DIALOG_BUTTON_NAME)
    main_button.setGeometry(30, 30, 100, 40)
    main_button.show()
    controller = _controller(host, _chapter(_target(_DIALOG_BUTTON_NAME)))
    dialog, _button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)

    controller.start()

    assert controller._overlay is not None
    assert controller._overlay.window() is host
    controller.stop()


def _nested_dialogs(host: QWidget) -> tuple[QDialog, QPushButton, QDialog, QPushButton]:
    outer = QDialog(host)
    outer.setObjectName("outerDialog")
    outer.setModal(True)
    outer.resize(360, 220)
    outer_button = QPushButton("Add", outer)
    outer_button.setObjectName("outerButton")
    outer_button.setGeometry(20, 20, 120, 40)
    inner = QDialog(outer)
    inner.setObjectName("innerDialog")
    inner.setModal(True)
    inner.resize(260, 160)
    inner_button = QPushButton("OK", inner)
    inner_button.setObjectName("innerButton")
    inner_button.setGeometry(20, 20, 120, 40)
    return outer, outer_button, inner, inner_button


def _fallback_chapter(requires: TutorialCompletion | None = None) -> TutorialChapter:
    return TutorialChapter(
        chapter_id="fallback",
        title_source="Fallback",
        destination=TutorialDestination(mode=EditingMode.IDENTIFY),
        steps=(
            TutorialStep(
                targets=(
                    TutorialTarget(
                        object_name="innerButton",
                        role=TutorialTargetRole.INTERACT,
                        prominence=TutorialTargetProminence.PRIMARY,
                        fallback_object_names=("outerButton",),
                    ),
                ),
                action_source="Confirm the inner dialog",
                expected_source="The inner dialog closes",
                advance=AdvanceTrigger.DIALOG_HIDDEN,
                advance_dialog="innerDialog",
                requires=requires,
            ),
            TutorialStep(
                targets=(),
                action_source="Back on the outer dialog",
                expected_source="The tour continues",
            ),
        ),
    )


def test_primary_target_wins_while_its_dialog_is_open(qtbot: QtBot) -> None:
    host = _shown_host(qtbot)
    controller = _controller(host, _fallback_chapter())
    controller.start()
    outer, _outer_button, inner, inner_button = _nested_dialogs(host)
    outer.show()
    qtbot.waitExposed(outer)
    inner.show()
    qtbot.waitExposed(inner)

    _wait_for_overlay_window(qtbot, controller, inner)
    assert controller._overlay is not None
    primary = controller._overlay.primary_spotlight_rect()
    assert primary is not None
    assert primary.contains(inner_button.mapTo(inner, inner_button.rect().center()))
    controller.stop()


def test_primary_target_falls_back_when_its_dialog_is_closed(qtbot: QtBot) -> None:
    """A closed dialog must not strand the coach marks on a hidden window."""
    host = _shown_host(qtbot)
    controller = _controller(host, _fallback_chapter(TutorialCompletion.PRESET_HAS_TUTORIAL_LINES))
    controller.start()
    outer, outer_button, inner, _inner_button = _nested_dialogs(host)
    outer.show()
    qtbot.waitExposed(outer)
    inner.show()
    qtbot.waitExposed(inner)
    _wait_for_overlay_window(qtbot, controller, inner)

    inner.reject()

    _wait_for_overlay_window(qtbot, controller, outer)
    assert controller._bubble is not None
    assert controller._bubble.window() is outer
    assert controller._overlay is not None
    primary = controller._overlay.primary_spotlight_rect()
    assert primary is not None
    assert primary.contains(outer_button.mapTo(outer, outer_button.rect().center()))
    controller.stop()


def test_dialog_hide_does_not_advance_while_the_gate_is_unmet(qtbot: QtBot) -> None:
    """Cancelling the dialog must leave a gated step in place."""
    host = _shown_host(qtbot)
    controller = _controller(
        host,
        _fallback_chapter(TutorialCompletion.PRESET_HAS_TUTORIAL_LINES),
        completion_checks={TutorialCompletion.PRESET_HAS_TUTORIAL_LINES: lambda: False},
    )
    controller.start()
    outer, _outer_button, inner, _inner_button = _nested_dialogs(host)
    outer.show()
    qtbot.waitExposed(outer)
    inner.show()
    qtbot.waitExposed(inner)
    _wait_for_overlay_window(qtbot, controller, inner)

    inner.reject()
    qtbot.wait(20)

    assert controller._step_index == 0
    controller.stop()


def test_open_gate_alone_does_not_advance_before_the_dialog_trigger(qtbot: QtBot) -> None:
    """A met condition never advances a step whose dialog trigger has not fired."""
    host = _shown_host(qtbot)
    met = False
    controller = _controller(
        host,
        _fallback_chapter(TutorialCompletion.PRESET_HAS_TUTORIAL_LINES),
        completion_checks={TutorialCompletion.PRESET_HAS_TUTORIAL_LINES: lambda: met},
    )
    controller.start()
    outer, _outer_button, inner, _inner_button = _nested_dialogs(host)
    outer.show()
    qtbot.waitExposed(outer)
    inner.show()
    qtbot.waitExposed(inner)
    _wait_for_overlay_window(qtbot, controller, inner)

    met = True
    qtbot.wait(400)

    assert controller._step_index == 0
    controller.stop()


def test_dialog_hide_advances_once_the_gate_opens_after_the_hide(qtbot: QtBot) -> None:
    """A dialog applies its result after hiding, so the held trigger advances then."""
    host = _shown_host(qtbot)
    met = False
    controller = _controller(
        host,
        _fallback_chapter(TutorialCompletion.PRESET_HAS_TUTORIAL_LINES),
        completion_checks={TutorialCompletion.PRESET_HAS_TUTORIAL_LINES: lambda: met},
    )
    controller.start()
    outer, _outer_button, inner, _inner_button = _nested_dialogs(host)
    outer.show()
    qtbot.waitExposed(outer)
    inner.show()
    qtbot.waitExposed(inner)
    _wait_for_overlay_window(qtbot, controller, inner)

    inner.accept()
    met = True

    qtbot.waitUntil(lambda: controller._step_index == 1)
    controller.stop()


def test_cancelled_dialog_advances_after_the_retry_satisfies_the_gate(qtbot: QtBot) -> None:
    """Cancelling holds the step; redoing the work in the reopened dialog resumes it."""
    host = _shown_host(qtbot)
    met = False
    controller = _controller(
        host,
        _fallback_chapter(TutorialCompletion.PRESET_HAS_TUTORIAL_LINES),
        completion_checks={TutorialCompletion.PRESET_HAS_TUTORIAL_LINES: lambda: met},
    )
    controller.start()
    outer, _outer_button, inner, _inner_button = _nested_dialogs(host)
    outer.show()
    qtbot.waitExposed(outer)
    inner.show()
    qtbot.waitExposed(inner)
    _wait_for_overlay_window(qtbot, controller, inner)
    inner.reject()
    qtbot.wait(20)
    assert controller._step_index == 0

    inner.show()
    qtbot.waitExposed(inner)
    inner.accept()
    met = True

    qtbot.waitUntil(lambda: controller._step_index == 1)
    controller.stop()


def test_split_related_targets_anchor_on_the_active_modal_window(qtbot: QtBot) -> None:
    """With the primary target gone, related targets in two windows still pick one host."""
    host = _shown_host(qtbot)
    main_button = QPushButton("Main", host)
    main_button.setObjectName("relatedMainTarget")
    main_button.setGeometry(30, 30, 100, 40)
    main_button.show()
    chapter = _chapter(
        _target("neverPresentButton"),
        _target("relatedMainTarget", TutorialTargetProminence.RELATED),
        _target(_DIALOG_BUTTON_NAME, TutorialTargetProminence.RELATED),
    )
    controller = _controller(host, chapter)
    dialog, _button = _modal_dialog(host)
    dialog.show()
    qtbot.waitExposed(dialog)

    controller.start()

    _wait_for_overlay_window(qtbot, controller, dialog)
    assert controller._bubble is not None
    assert controller._bubble.window() is dialog
    controller.stop()


def test_unresolvable_target_anchors_on_the_active_modal_window(qtbot: QtBot) -> None:
    """With no target left, the bubble must stay on the dialog the user is in."""
    host = _shown_host(qtbot)
    dialog, _button = _modal_dialog(host)
    dialog.setObjectName("someDialog")
    dialog.show()
    qtbot.waitExposed(dialog)
    controller = _controller(host, _chapter(_target("neverPresentButton")))

    controller.start()

    _wait_for_overlay_window(qtbot, controller, dialog)
    assert controller._bubble is not None
    assert controller._bubble.window() is dialog
    controller.stop()
