"""The rectangle-zoom gate must ignore the preceding step's keyboard navigation.

The getting_started chapter tells the user to zoom and pan with the wheel and
the arrow keys one step before the rectangle-zoom step. A gate phrased as
"the visible range differs from the full extent" is therefore already met when
the gated step opens, so the condition is anchored on the undo history's range
change source instead.
"""

from __future__ import annotations

import pytest

from chappy.application.spectrum import SpectrumRangeSource
from chappy.application.spectrum.models import (
    PanNavigationIntent,
    RangeNavigationIntent,
    RangeNavigationRequest,
    ZoomFactorNavigationIntent,
    ZoomRectNavigationIntent,
)
from chappy.application.spectrum.range_usecase import RangeNavigationUseCase
from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
from chappy.gui.shell.composition import create_main_window
from chappy.gui.shell.dependencies import ShellDependencies
from chappy.gui.shell.tutorial_chapters import build_full_walkthrough_chapters
from chappy.infrastructure.composition import create_default_infrastructure_dependencies

_FULL_RANGE = (4000.0, 5000.0)
_ZOOMED_RANGE = (4700.0, 4800.0)


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (PanNavigationIntent(fraction=0.1), SpectrumRangeSource.INTENT),
        (ZoomFactorNavigationIntent(factor=1.2), SpectrumRangeSource.INTENT),
        (
            ZoomRectNavigationIntent(min_wavelength=4700.0, max_wavelength=4800.0),
            SpectrumRangeSource.RECT_ZOOM,
        ),
    ],
)
def test_only_a_rectangle_intent_is_classified_as_rect_zoom(
    intent: RangeNavigationIntent, expected: SpectrumRangeSource
) -> None:
    """Arrow-key and wheel navigation must not borrow the rectangle zoom's source."""
    result = RangeNavigationUseCase().calculate(
        RangeNavigationRequest(current_range=_FULL_RANGE, intent=intent, data_bounds=_FULL_RANGE)
    )

    assert result.source is expected


def _window(qtbot):
    dependencies = create_default_infrastructure_dependencies(translate_presets=str)
    window = create_main_window(
        ShellDependencies(
            project_io_usecase=dependencies.project_io_usecase,
            atomic_data=dependencies.atomic_repository,
            preset_store=IdentifyPresetStore(dependencies.preset_store),
            optimize_model_addition_usecase=dependencies.optimize_model_addition_usecase,
        )
    )
    qtbot.addWidget(window)
    return window


def test_keyboard_navigation_alone_does_not_open_the_rectangle_zoom_gate(qtbot) -> None:
    window = _window(qtbot)
    window._history_recorder.record_range_change(
        _FULL_RANGE, _ZOOMED_RANGE, None, None, SpectrumRangeSource.INTENT.value
    )

    assert not window._tutorial_rect_zoom_applied()


def test_a_rectangle_zoom_opens_the_gate(qtbot) -> None:
    window = _window(qtbot)
    window._history_recorder.record_range_change(
        _FULL_RANGE, _ZOOMED_RANGE, None, None, SpectrumRangeSource.RECT_ZOOM.value
    )

    assert window._tutorial_rect_zoom_applied()


def test_the_gate_stays_open_when_navigation_follows_the_rectangle_zoom(qtbot) -> None:
    """Panning after the zoom must not re-lock a step the user already completed."""
    window = _window(qtbot)
    window._history_recorder.record_range_change(
        _FULL_RANGE, _ZOOMED_RANGE, None, None, SpectrumRangeSource.RECT_ZOOM.value
    )
    window._history_recorder.record_range_change(
        _ZOOMED_RANGE, (4750.0, 4850.0), None, None, SpectrumRangeSource.INTENT.value
    )

    assert window._tutorial_rect_zoom_applied()


def test_the_rectangle_zoom_step_directly_follows_the_keyboard_navigation_step() -> None:
    """Guards the adjacency that makes a range-extent gate unusable here."""
    getting_started = next(
        chapter
        for chapter in build_full_walkthrough_chapters()
        if chapter.chapter_id == "getting_started"
    )
    keyboard_index = next(
        index
        for index, step in enumerate(getting_started.steps)
        if "Up/Down arrow keys" in step.action_source
    )
    rect_index = next(
        index
        for index, step in enumerate(getting_started.steps)
        if "first click this Zoom button" in step.action_source
    )

    assert rect_index == keyboard_index + 1
