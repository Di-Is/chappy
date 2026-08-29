"""Tests for tutorial step retreat and chapter prerequisite soft-blocking."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from chappy.core.editing_mode import EditingMode
from chappy.gui.common.shared_operations import AnalysisOperationPanel, AnalysisOperationSurface
from chappy.gui.common.tutorial import (
    AdvanceTrigger,
    TutorialChapter,
    TutorialDestination,
    TutorialPrerequisite,
    TutorialStep,
)
from chappy.gui.shell.tutorial_tour_controller import TutorialTourController


def _step(advance: AdvanceTrigger = AdvanceTrigger.NEXT_BUTTON) -> TutorialStep:
    if advance is AdvanceTrigger.MODE_CHANGE:
        return TutorialStep(
            targets=(),
            action_source="Action",
            expected_source="Result",
            advance=advance,
            advance_mode=EditingMode.ANALYSIS,
        )
    return TutorialStep(targets=(), action_source="Action", expected_source="Result")


def _chapter(
    chapter_id: str,
    *,
    destination: TutorialDestination,
    steps: tuple[TutorialStep, ...],
    prerequisite: TutorialPrerequisite | None = None,
) -> TutorialChapter:
    return TutorialChapter(
        chapter_id=chapter_id,
        title_source=chapter_id,
        destination=destination,
        steps=steps,
        prerequisite=prerequisite,
    )


def _controller(
    host: QWidget,
    chapters: tuple[TutorialChapter, ...],
    *,
    calls: list[object] | None = None,
    prerequisite_checks: dict[TutorialPrerequisite, object] | None = None,
    chapter_context_changed: object | None = None,
) -> TutorialTourController:
    recorded = calls if calls is not None else []

    def record_surface(surface: AnalysisOperationSurface) -> bool:
        recorded.append(surface)
        return True

    def record_panel(panel: AnalysisOperationPanel) -> bool:
        recorded.append(panel)
        return True

    return TutorialTourController(
        host,
        chapters=chapters,
        switch_mode=recorded.append,
        switch_analysis_surface=record_surface,
        switch_analysis_panel=record_panel,
        chapter_context_changed=chapter_context_changed,  # type: ignore[arg-type]
        prerequisite_checks=prerequisite_checks,  # type: ignore[arg-type]
    )


def test_back_is_disabled_only_on_the_tour_first_step(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    chapters = (
        _chapter(
            "first",
            destination=TutorialDestination(mode=EditingMode.IDENTIFY),
            steps=(_step(), _step()),
        ),
    )
    controller = _controller(host, chapters)

    controller.start()
    assert controller._bubble is not None
    assert not controller._bubble._back_button.isEnabled()

    controller._advance()
    assert controller._bubble._back_button.isEnabled()


def test_back_retreats_within_a_chapter_without_reapplying_destination(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    calls: list[object] = []
    chapters = (
        _chapter(
            "first",
            destination=TutorialDestination(mode=EditingMode.IDENTIFY),
            steps=(_step(), _step()),
        ),
    )
    controller = _controller(host, chapters, calls=calls)

    controller.start()
    controller._advance()
    assert controller._bubble is not None
    controller._bubble.back_requested.emit()

    assert controller._step_index == 0
    assert calls == [EditingMode.IDENTIFY]


def test_back_across_chapters_reapplies_previous_destination(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    calls: list[object] = []
    contexts: list[str | None] = []
    chapters = (
        _chapter(
            "analysis",
            destination=TutorialDestination(
                mode=EditingMode.ANALYSIS,
                surface=AnalysisOperationSurface.OVERVIEW,
                panel=AnalysisOperationPanel.SUMMARY,
            ),
            steps=(_step(), _step()),
        ),
        _chapter(
            "continuum",
            destination=TutorialDestination(mode=EditingMode.CONTINUUM),
            steps=(_step(),),
        ),
    )
    controller = _controller(host, chapters, calls=calls, chapter_context_changed=contexts.append)

    controller.start()
    controller._advance()
    controller._advance()
    assert controller._current_chapter().chapter_id == "continuum"

    assert controller._bubble is not None
    controller._bubble.back_requested.emit()

    assert controller._current_chapter().chapter_id == "analysis"
    assert controller._step_index == 1
    assert calls == [
        EditingMode.ANALYSIS,
        AnalysisOperationSurface.OVERVIEW,
        AnalysisOperationPanel.SUMMARY,
        EditingMode.CONTINUUM,
        EditingMode.ANALYSIS,
        AnalysisOperationSurface.OVERVIEW,
        AnalysisOperationPanel.SUMMARY,
    ]
    assert contexts == ["analysis", "continuum", "analysis"]


def test_back_onto_mode_change_step_restores_its_wait_state(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    chapters = (
        _chapter(
            "identify",
            destination=TutorialDestination(mode=EditingMode.IDENTIFY),
            steps=(_step(), _step(AdvanceTrigger.MODE_CHANGE)),
        ),
        _chapter(
            "analysis",
            destination=TutorialDestination(
                mode=EditingMode.ANALYSIS,
                surface=AnalysisOperationSurface.OVERVIEW,
                panel=AnalysisOperationPanel.SUMMARY,
            ),
            steps=(_step(),),
        ),
    )
    controller = _controller(host, chapters)

    controller.start()
    controller._advance()
    controller.notify_mode_changed(EditingMode.ANALYSIS)
    assert controller._current_chapter().chapter_id == "analysis"

    assert controller._bubble is not None
    controller._bubble.back_requested.emit()

    assert controller._current_chapter().chapter_id == "identify"
    assert controller._step_index == 1
    assert not controller._bubble._next_button.isEnabled()

    controller.notify_mode_changed(EditingMode.ANALYSIS)
    assert controller._current_chapter().chapter_id == "analysis"


def test_unmet_prerequisite_shows_warning_before_applying_destination(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    calls: list[object] = []
    contexts: list[str | None] = []
    chapters = (
        _chapter(
            "identify",
            destination=TutorialDestination(mode=EditingMode.IDENTIFY),
            steps=(_step(),),
        ),
        _chapter(
            "analysis",
            destination=TutorialDestination(
                mode=EditingMode.ANALYSIS,
                surface=AnalysisOperationSurface.OVERVIEW,
                panel=AnalysisOperationPanel.SUMMARY,
            ),
            steps=(_step(),),
            prerequisite=TutorialPrerequisite.HAS_CONFIRMED_REGION,
        ),
    )
    controller = _controller(
        host,
        chapters,
        calls=calls,
        prerequisite_checks={TutorialPrerequisite.HAS_CONFIRMED_REGION: lambda: False},
        chapter_context_changed=contexts.append,
    )

    controller.start()
    controller._advance()

    assert controller._awaiting_prerequisite
    assert controller.is_active
    assert calls == [EditingMode.IDENTIFY]
    assert contexts == ["identify"]
    assert controller._bubble is not None
    assert controller._bubble._next_button.text() == "Continue anyway"
    assert "none has been registered yet" in controller._bubble._action_label.text()
    assert not controller._bubble._expected_label.isVisibleTo(controller._bubble)
    assert controller._bubble._back_button.isEnabled()


def test_missing_prerequisite_check_counts_as_unmet(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    chapters = (
        _chapter(
            "analysis",
            destination=TutorialDestination(
                mode=EditingMode.ANALYSIS,
                surface=AnalysisOperationSurface.OVERVIEW,
                panel=AnalysisOperationPanel.SUMMARY,
            ),
            steps=(_step(),),
            prerequisite=TutorialPrerequisite.HAS_CONFIRMED_REGION,
        ),
    )
    controller = _controller(host, chapters)

    controller.start()

    assert controller._awaiting_prerequisite
    assert controller._bubble is not None
    assert not controller._bubble._back_button.isEnabled()


def test_met_prerequisite_starts_the_chapter_normally(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    calls: list[object] = []
    chapters = (
        _chapter(
            "analysis",
            destination=TutorialDestination(
                mode=EditingMode.ANALYSIS,
                surface=AnalysisOperationSurface.OVERVIEW,
                panel=AnalysisOperationPanel.SUMMARY,
            ),
            steps=(_step(),),
            prerequisite=TutorialPrerequisite.HAS_CONFIRMED_REGION,
        ),
    )
    controller = _controller(
        host,
        chapters,
        calls=calls,
        prerequisite_checks={TutorialPrerequisite.HAS_CONFIRMED_REGION: lambda: True},
    )

    controller.start()

    assert not controller._awaiting_prerequisite
    assert calls == [
        EditingMode.ANALYSIS,
        AnalysisOperationSurface.OVERVIEW,
        AnalysisOperationPanel.SUMMARY,
    ]


def _blocked_two_chapter_tour(host: QWidget, calls: list[object]) -> TutorialTourController:
    chapters = (
        _chapter(
            "identify",
            destination=TutorialDestination(mode=EditingMode.IDENTIFY),
            steps=(_step(), _step()),
        ),
        _chapter(
            "analysis",
            destination=TutorialDestination(
                mode=EditingMode.ANALYSIS,
                surface=AnalysisOperationSurface.OVERVIEW,
                panel=AnalysisOperationPanel.SUMMARY,
            ),
            steps=(_step(),),
            prerequisite=TutorialPrerequisite.HAS_CONFIRMED_REGION,
        ),
    )
    return _controller(
        host,
        chapters,
        calls=calls,
        prerequisite_checks={TutorialPrerequisite.HAS_CONFIRMED_REGION: lambda: False},
    )


def test_continue_anyway_starts_the_blocked_chapter(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    calls: list[object] = []
    controller = _blocked_two_chapter_tour(host, calls)

    controller.start()
    controller._advance()
    controller._advance()
    assert controller._awaiting_prerequisite

    assert controller._bubble is not None
    controller._bubble.next_requested.emit()

    assert not controller._awaiting_prerequisite
    assert controller._current_chapter().chapter_id == "analysis"
    assert controller._step_index == 0
    assert calls == [
        EditingMode.IDENTIFY,
        EditingMode.ANALYSIS,
        AnalysisOperationSurface.OVERVIEW,
        AnalysisOperationPanel.SUMMARY,
    ]
    assert controller._bubble._next_button.text() == "Next"


def test_back_from_warning_resumes_previous_chapter_last_step(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    calls: list[object] = []
    controller = _blocked_two_chapter_tour(host, calls)

    controller.start()
    controller._advance()
    controller._advance()
    assert controller._awaiting_prerequisite

    assert controller._bubble is not None
    controller._bubble.back_requested.emit()

    assert not controller._awaiting_prerequisite
    assert controller._current_chapter().chapter_id == "identify"
    assert controller._step_index == 1
    assert calls == [EditingMode.IDENTIFY]
    assert controller._bubble._next_button.text() == "Next"
