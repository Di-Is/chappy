"""Semantic target coverage for walkthrough steps that span multiple UI areas."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from chappy.core.editing_mode import EditingMode
from chappy.gui.common.tutorial import (
    AdvanceTrigger,
    TutorialCompletion,
    TutorialSpotlightOverlay,
    TutorialSpotlightTarget,
    TutorialStep,
    TutorialTargetProminence,
    TutorialTargetRole,
)
from chappy.gui.shell.tutorial_chapters import (
    build_full_walkthrough_chapters,
    build_short_walkthrough_chapters,
)


@dataclass(frozen=True, slots=True)
class ExpectedTarget:
    object_name: str
    role: TutorialTargetRole


def _walkthrough_steps() -> dict[str, tuple[TutorialStep, ...]]:
    return {chapter.chapter_id: chapter.steps for chapter in build_full_walkthrough_chapters()}


def _step_with_text(chapter_id: str, action_fragment: str) -> TutorialStep:
    matches = [
        step for step in _walkthrough_steps()[chapter_id] if action_fragment in step.action_source
    ]
    assert len(matches) == 1, (chapter_id, action_fragment, len(matches))
    return matches[0]


@pytest.mark.parametrize(
    ("chapter_id", "action_fragment", "expected_targets"),
    [
        (
            "getting_started",
            "bundled sample spectrum",
            (
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
                ExpectedTarget("modeButton_IDENTIFY", TutorialTargetRole.CONTEXT),
            ),
        ),
        (
            "getting_started",
            "Use this button when you want",
            (ExpectedTarget("modeContextBar_open_observation_data", TutorialTargetRole.OBSERVE),),
        ),
        (
            "getting_started",
            "first click this Zoom button",
            (
                ExpectedTarget("modeContextBar_zoom_rect", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.INTERACT),
            ),
        ),
        (
            "getting_started",
            "Click [Undo]",
            (
                ExpectedTarget("modeContextBar_undo", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "getting_started",
            "Click [Redo]",
            (
                ExpectedTarget("modeContextBar_redo", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "getting_started",
            "type an exact wavelength range",
            (
                ExpectedTarget("dataControlPanel_wavelengthMinField", TutorialTargetRole.INTERACT),
                ExpectedTarget("dataControlPanel_wavelengthMaxField", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "getting_started",
            "click [Auto Adjust]",
            (
                ExpectedTarget("autoAdjustButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "getting_started",
            "Click [Reset View]",
            (
                ExpectedTarget("resetViewButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "identify",
            "Identify mode is active",
            (ExpectedTarget("modeButton_IDENTIFY", TutorialTargetRole.CONTEXT),),
        ),
        (
            "identify",
            'preset "Metal Lines"',
            (
                ExpectedTarget("identifyPresetCombo", TutorialTargetRole.INTERACT),
                ExpectedTarget("identifyReferenceLineCombo", TutorialTargetRole.OBSERVE),
                ExpectedTarget("identifyCandidateTable", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "identify",
            "Bring the 4755-4780",
            (
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.INTERACT),
                ExpectedTarget("dataControlPanel_wavelengthMinField", TutorialTargetRole.INTERACT),
                ExpectedTarget("dataControlPanel_wavelengthMaxField", TutorialTargetRole.INTERACT),
                ExpectedTarget("modeContextBar_zoom_rect", TutorialTargetRole.INTERACT),
                ExpectedTarget("autoAdjustButton", TutorialTargetRole.INTERACT),
            ),
        ),
        (
            "identify",
            "Hold Shift and hover",
            (
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.INTERACT),
                ExpectedTarget("identifyTemporarySection", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "identify",
            "Click [Register]",
            (
                ExpectedTarget("identifyTemporaryRegisterButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("identifyTemporarySection", TutorialTargetRole.OBSERVE),
                ExpectedTarget("identifyConfirmedSection", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "analysis_detail",
            "The region you just opened is shown here",
            (
                ExpectedTarget("analysisDetailRegionSelector", TutorialTargetRole.CONTEXT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
                ExpectedTarget("analysisDetailParameterTree", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "analysis_detail",
            "then click [Add Component]",
            (
                ExpectedTarget("analysisDetailParameterTree", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisDetailAddModelButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "analysis_detail",
            "Give the fit a starting point",
            (
                ExpectedTarget("analysisDetailParameterTree", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.INTERACT),
            ),
        ),
        (
            "analysis_detail",
            "Click [Fit]",
            (
                ExpectedTarget("analysisDetailFitButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
                ExpectedTarget("analysisDetailParameterTree", TutorialTargetRole.OBSERVE),
                ExpectedTarget("analysisDetailResultsCard", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "preset_build",
            "click this preset management button",
            (ExpectedTarget("identifyManagePresetButton", TutorialTargetRole.INTERACT),),
        ),
        (
            "preset_build",
            "Click [Add Line]",
            (ExpectedTarget("presetAddLineButton", TutorialTargetRole.INTERACT),),
        ),
        (
            "preset_build",
            "Filter by rest wavelength",
            (
                ExpectedTarget("filterWavelengthRange", TutorialTargetRole.INTERACT),
                ExpectedTarget("filterElementCombo", TutorialTargetRole.INTERACT),
                ExpectedTarget("filterStageCombo", TutorialTargetRole.INTERACT),
                ExpectedTarget("lineResultTable", TutorialTargetRole.INTERACT),
            ),
        ),
        (
            "preset_build",
            "click [Link selected lines]",
            (
                ExpectedTarget("presetAddTieGroupButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("presetLineTable", TutorialTargetRole.INTERACT),
            ),
        ),
        (
            "velocity_identify",
            "press V to open the velocity plot",
            (ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.INTERACT),),
        ),
        (
            "velocity_identify",
            "Click [Add selected lines to temporary list]",
            (
                ExpectedTarget("velocityPlotCreateButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("identifyTemporarySection", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "velocity_identify",
            "Click [Register]",
            (
                ExpectedTarget("identifyTemporaryRegisterButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("identifyConfirmedSection", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "analysis_structure",
            "Back in Analysis",
            (
                ExpectedTarget("analysisOverviewReviewWidget", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisOverviewEditStructureButton", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "analysis_structure",
            "Click [Edit region]",
            (
                ExpectedTarget("analysisOverviewEditStructureButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisStructureTree", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "analysis_structure",
            "Click [Merge].",
            (
                ExpectedTarget("analysisOverviewMergeButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisStructureTree", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "analysis_structure",
            "click [Split]",
            (
                ExpectedTarget("analysisOverviewSplitButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisStructureTree", TutorialTargetRole.INTERACT),
            ),
        ),
        (
            "analysis_structure",
            "When you are done",
            (
                ExpectedTarget("organizeSidePanelBackButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisOverviewReviewWidget", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "joint_fit",
            "choose [Share z]",
            (ExpectedTarget("analysisDetailParameterTree", TutorialTargetRole.INTERACT),),
        ),
        (
            "joint_fit",
            "fit all six lines",
            (
                ExpectedTarget("analysisDetailFitButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
                ExpectedTarget("analysisDetailParameterTree", TutorialTargetRole.OBSERVE),
                ExpectedTarget("analysisDetailResultsCard", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "joint_fit",
            "Fix logN",
            (
                ExpectedTarget("analysisDetailParameterTree", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisDetailFitButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("analysisDetailResultsCard", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "continuum",
            "Continuum mode is active",
            (
                ExpectedTarget("continuumPointsTable", TutorialTargetRole.CONTEXT),
                ExpectedTarget("modeButton_CONTINUUM", TutorialTargetRole.CONTEXT),
            ),
        ),
        (
            "continuum",
            "Click [Auto Estimate]",
            (
                ExpectedTarget("continuumAutoEstimateButton", TutorialTargetRole.INTERACT),
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.OBSERVE),
                ExpectedTarget("continuumPointsTable", TutorialTargetRole.OBSERVE),
            ),
        ),
        (
            "continuum",
            "Double-click on the spectrum",
            (
                ExpectedTarget("spectrumPlotContainer", TutorialTargetRole.INTERACT),
                ExpectedTarget("continuumPointsTable", TutorialTargetRole.OBSERVE),
            ),
        ),
    ],
)
def test_walkthrough_problem_steps_highlight_every_required_area(
    chapter_id: str, action_fragment: str, expected_targets: tuple[ExpectedTarget, ...]
) -> None:
    """Every audited instruction exposes all areas needed to act and verify."""
    step = _step_with_text(chapter_id, action_fragment)

    actual = tuple(ExpectedTarget(target.object_name, target.role) for target in step.targets)

    assert actual == expected_targets


def test_every_targeted_walkthrough_step_has_exactly_one_primary() -> None:
    """Each target group has one unambiguous bubble anchor."""
    for steps in _walkthrough_steps().values():
        for step in steps:
            primary_count = sum(
                target.prominence is TutorialTargetProminence.PRIMARY for target in step.targets
            )
            assert primary_count == (1 if step.targets else 0)


def test_short_walkthrough_covers_the_minimal_loop() -> None:
    chapter_ids = [chapter.chapter_id for chapter in build_short_walkthrough_chapters()]

    assert chapter_ids == ["getting_started", "identify", "analysis", "analysis_detail", "save"]


def test_full_walkthrough_extends_the_short_one_with_the_low_z_absorber_flow() -> None:
    chapter_ids = [chapter.chapter_id for chapter in build_full_walkthrough_chapters()]

    assert chapter_ids == [
        "getting_started",
        "identify",
        "analysis",
        "analysis_detail",
        "preset_build",
        "velocity_identify",
        "analysis_structure",
        "joint_fit",
        "continuum",
        "save",
    ]


def test_shared_chapters_have_a_single_definition() -> None:
    """Chapters common to both walkthroughs must come from the same source."""
    full_chapters = {chapter.chapter_id: chapter for chapter in build_full_walkthrough_chapters()}

    for chapter in build_short_walkthrough_chapters():
        assert chapter == full_chapters[chapter.chapter_id]


def test_both_walkthroughs_teach_undo_and_redo_after_rectangle_zoom() -> None:
    """Both paths must exercise reversible navigation before later workflows diverge."""
    expected_fragments = (
        "then drag a rectangle",
        "Click [Undo]",
        "Click [Redo]",
        "type an exact wavelength range",
    )

    for builder in (build_short_walkthrough_chapters, build_full_walkthrough_chapters):
        getting_started = next(
            chapter for chapter in builder() if chapter.chapter_id == "getting_started"
        )
        matching_indices = tuple(
            next(
                index
                for index, step in enumerate(getting_started.steps)
                if fragment in step.action_source
            )
            for fragment in expected_fragments
        )
        assert matching_indices == tuple(sorted(matching_indices))


def test_wavelength_entry_instructions_match_the_unlabelled_field_layout() -> None:
    """Tutorial copy identifies wavelength fields by position, not absent labels."""
    action_sources = (
        step.action_source
        for chapter in build_full_walkthrough_chapters()
        for step in chapter.steps
    )

    for action_source in action_sources:
        assert "Min/Max" not in action_source
        assert "type Min " not in action_source


@pytest.mark.parametrize(
    ("chapter_id", "action_fragment", "expected_mode"),
    [
        ("identify", "Click [Analysis]", EditingMode.ANALYSIS),
        ("joint_fit", "Click [Continuum]", EditingMode.CONTINUUM),
    ],
)
def test_walkthrough_mode_transitions_wait_for_the_expected_mode(
    chapter_id: str, action_fragment: str, expected_mode: EditingMode
) -> None:
    step = _step_with_text(chapter_id, action_fragment)

    assert step.advance is AdvanceTrigger.MODE_CHANGE
    assert step.advance_mode is expected_mode


def test_each_chapter_asks_its_checkpoint_once_on_the_step_that_earns_it() -> None:
    """A trailing navigation step must not carry the question about the work before it."""
    for chapter in build_full_walkthrough_chapters():
        checkpoint_steps = [step for step in chapter.steps if step.checkpoint_source is not None]
        assert len(checkpoint_steps) <= 1
        for step in checkpoint_steps:
            assert step.advance is not AdvanceTrigger.MODE_CHANGE


def test_joint_fit_asks_about_the_fit_then_hands_over_to_continuum() -> None:
    joint_fit_steps = _walkthrough_steps()["joint_fit"]

    fit_step = _step_with_text("joint_fit", "Fix logN")
    assert fit_step.checkpoint_source is not None
    assert any(target.object_name == "analysisDetailResultsCard" for target in fit_step.targets)
    assert joint_fit_steps[-1].advance is AdvanceTrigger.MODE_CHANGE


def test_analysis_reviews_readiness_then_opens_the_region_by_hand() -> None:
    """Reading the status has no outcome of its own, so it shares the [Open region] step."""
    analysis_steps = _walkthrough_steps()["analysis"]

    assert len(analysis_steps) == 1
    step = analysis_steps[0]
    assert "Analysis status" in step.action_source
    assert "[Open region]" in step.action_source
    assert tuple(target.object_name for target in step.targets) == (
        "analysisOverviewReviewWidget",
        "analysisOverviewStatusCard",
        "analysisOverviewOpenRegionButton",
    )
    assert step.requires is TutorialCompletion.REGION_DETAIL_OPENED


def test_analysis_detail_asks_about_the_fit_on_the_fit_step() -> None:
    detail_steps = _walkthrough_steps()["analysis_detail"]

    assert len(detail_steps) == 4
    last = detail_steps[-1]
    assert last.checkpoint_source is not None
    assert "Click [Fit]" in last.action_source
    assert last.requires is TutorialCompletion.REGION_FIT_APPLIED
    assert "[Export Results]" in last.action_source


def test_component_addition_is_one_step_from_selection_to_the_button() -> None:
    """Selecting a line has no outcome of its own, so it shares the [Add Component] step."""
    detail_steps = _walkthrough_steps()["analysis_detail"]

    add_steps = [step for step in detail_steps if "[Add Component]" in step.action_source]
    assert len(add_steps) == 1
    assert add_steps[0].requires is TutorialCompletion.REGION_HAS_COMPONENT


def test_identify_navigation_leaves_every_zoom_route_usable() -> None:
    """The step states a target range, so each taught zoom route must stay unmasked."""
    step = _step_with_text("identify", "Bring the 4755-4780")

    assert tuple(target.object_name for target in step.targets) == (
        "spectrumPlotContainer",
        "dataControlPanel_wavelengthMinField",
        "dataControlPanel_wavelengthMaxField",
        "modeContextBar_zoom_rect",
        "autoAdjustButton",
    )
    assert step.targets[0].prominence is TutorialTargetProminence.PRIMARY
    assert all(
        target.prominence is TutorialTargetProminence.RELATED for target in step.targets[1:]
    )
    assert all(target.role is TutorialTargetRole.INTERACT for target in step.targets)
    assert step.operation is None
    assert step.advance is AdvanceTrigger.NEXT_BUTTON


def test_identify_entry_uses_mode_badge_as_primary_context() -> None:
    step = _step_with_text("identify", "Identify mode is active")

    assert tuple(target.object_name for target in step.targets) == ("modeButton_IDENTIFY",)
    assert all(target.role is TutorialTargetRole.CONTEXT for target in step.targets)
    assert step.targets[0].prominence is TutorialTargetProminence.PRIMARY


def test_identify_gates_the_preset_and_reference_line_the_later_chapters_name() -> None:
    """Skipping either selection makes every later C IV instruction unfollowable."""
    preset_step = _step_with_text("identify", 'preset "Metal Lines"')
    reference_step = _step_with_text("identify", "C IV 1548.204 as the reference line")

    assert preset_step.requires is TutorialCompletion.METAL_LINES_PRESET_SELECTED
    assert reference_step.requires is TutorialCompletion.REFERENCE_LINE_IS_CIV1548
    assert preset_step.advance is AdvanceTrigger.NEXT_BUTTON
    assert reference_step.advance is AdvanceTrigger.NEXT_BUTTON


def test_identify_asks_about_the_registration_then_hands_over_to_analysis() -> None:
    identify_steps = _walkthrough_steps()["identify"]

    assert len(identify_steps) == 7
    register = _step_with_text("identify", "Click [Register]")
    assert register.checkpoint_source is not None
    assert register.advance is AdvanceTrigger.NEXT_BUTTON
    assert register.requires is TutorialCompletion.CONFIRMED_REGION_EXISTS
    assert any(target.object_name == "identifyConfirmedSection" for target in register.targets)
    assert identify_steps[-1].advance is AdvanceTrigger.MODE_CHANGE
    assert all("Right Arrow" not in step.action_source for step in identify_steps)


def _click_topmost_at(widget: QWidget, qtbot) -> QWidget:
    global_position = widget.mapToGlobal(widget.rect().center())
    receiver = QApplication.widgetAt(global_position)
    assert receiver is not None
    qtbot.mouseClick(
        receiver, Qt.MouseButton.LeftButton, pos=receiver.mapFromGlobal(global_position)
    )
    return receiver


def test_identify_interactions_pass_targets_and_block_dimmed_area(qtbot) -> None:
    target_names = (
        "dataControlPanel_wavelengthMinField",
        "dataControlPanel_wavelengthMaxField",
        "modeContextBar_zoom_rect",
        "autoAdjustButton",
        "spectrumPlotContainer",
    )
    step = _step_with_text("identify", "Bring the 4755-4780")
    window = QWidget()
    window.resize(700, 420)
    qtbot.addWidget(window)
    widgets: dict[str, QPushButton] = {}
    for object_name, geometry in (
        ("dataControlPanel_wavelengthMinField", (30, 200, 100, 30)),
        ("dataControlPanel_wavelengthMaxField", (140, 200, 100, 30)),
        ("modeContextBar_zoom_rect", (30, 20, 100, 30)),
        ("autoAdjustButton", (30, 70, 220, 120)),
        ("spectrumPlotContainer", (300, 120, 320, 220)),
    ):
        widget = QPushButton(object_name, window)
        widget.setObjectName(object_name)
        widget.setGeometry(*geometry)
        widgets[object_name] = widget
    dimmed = QPushButton("Dimmed", window)
    dimmed.setGeometry(30, 300, 140, 40)
    window.show()
    qtbot.waitExposed(window)
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets(
        tuple(
            TutorialSpotlightTarget(
                widget=widgets[target.object_name], role=target.role, prominence=target.prominence
            )
            for target in step.targets
        )
    )
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()

    for object_name in target_names:
        widget = widgets[object_name]
        with qtbot.waitSignal(widget.clicked):
            receiver = _click_topmost_at(widget, qtbot)
        assert receiver is widget

    dimmed_global = dimmed.mapToGlobal(QPoint(dimmed.width() // 2, dimmed.height() // 2))
    receiver = QApplication.widgetAt(dimmed_global)
    assert receiver is overlay
    with qtbot.assertNotEmitted(dimmed.clicked):
        qtbot.mouseClick(
            receiver, Qt.MouseButton.LeftButton, pos=receiver.mapFromGlobal(dimmed_global)
        )
