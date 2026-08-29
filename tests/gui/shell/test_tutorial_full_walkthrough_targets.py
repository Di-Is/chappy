"""Headless chapter-order walk of the full walkthrough on the real main window.

Drives the composed application window through every full-walkthrough chapter,
opening the real modal dialogs at their dialog-transition steps, and verifies
that every chapter destination applies and that no coach-mark target fails to
resolve.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from chappy.gui.common.tutorial import (
    AdvanceTrigger,
    TutorialCompletion,
    TutorialPrerequisite,
    TutorialTargetRole,
)
from chappy.gui.dialogs.line_selection_dialog import LineSelectionDialog
from chappy.gui.modes.identify.presets.preset_list_dialog import PresetListDialog
from chappy.gui.modes.identify.presets.preset_store import IdentifyPresetStore
from chappy.gui.shell.composition import create_main_window
from chappy.gui.shell.dependencies import ShellDependencies
from chappy.gui.shell.main_window import (
    _SAMPLE_RESOLVING_POWER,
    MainWindow,
    _find_sample_spectrum_pair,
)
from chappy.gui.shell.tutorial_chapters import build_full_walkthrough_chapters
from chappy.gui.spectrum.velocity.overlay_widget import SpectrumVelocityOverlayWidget
from chappy.infrastructure.composition import create_default_infrastructure_dependencies

if TYPE_CHECKING:
    from collections.abc import Mapping

    from PySide6.QtWidgets import QWidget

    from chappy.gui.common.tutorial import TutorialStep
    from chappy.gui.shell.main_window import ChappyMain
    from chappy.gui.shell.tutorial_tour_controller import TutorialTourController

_MAX_WALK_ACTIONS = 200

_TOUR_LOGGER = "chappy.gui.shell.tutorial_tour_controller"


def _prepare_window(qtbot) -> tuple[ChappyMain, IdentifyPresetStore, object]:
    dependencies = create_default_infrastructure_dependencies(translate_presets=str)
    preset_store = IdentifyPresetStore(dependencies.preset_store)
    window = create_main_window(
        ShellDependencies(
            project_io_usecase=dependencies.project_io_usecase,
            atomic_data=dependencies.atomic_repository,
            preset_store=preset_store,
            optimize_model_addition_usecase=dependencies.optimize_model_addition_usecase,
        )
    )
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()
    qtbot.waitExposed(window)
    return window, preset_store, dependencies.atomic_repository


def _load_sample_with_one_region(window: ChappyMain) -> None:
    sample_pair = _find_sample_spectrum_pair()
    assert sample_pair is not None, "bundled sample spectrum is missing"
    flux_path, error_path = sample_pair
    window._require_project_session().open_sample_data(
        str(flux_path), str(error_path), resolving_power=_SAMPLE_RESOLVING_POWER
    )
    project = window.current_project
    assert project is not None
    line = project.add_absorption_line(
        species="C IV",
        rest_wavelength=1548.204,
        center_z=2.0764,
        window_kms=200.0,
        multiplet_label="C IV",
        transition_name="C IV 1548",
        oscillator_strength=0.19,
        gamma_value=2.643e8,
        lambda_range=(4760.0, 4766.0),
    )
    project.create_region_with_lines([line.line_id])


def _apply_step_advance(
    window: ChappyMain,
    controller: TutorialTourController,
    step: TutorialStep,
    dialogs: Mapping[str, QWidget],
) -> None:
    """Perform the user action the step waits for, so the walk moves on."""
    if step.advance is AdvanceTrigger.NEXT_BUTTON:
        controller._advance()
    elif step.advance is AdvanceTrigger.MODE_CHANGE:
        assert step.advance_mode is not None
        window.switch_mode(step.advance_mode)
    elif step.advance is AdvanceTrigger.DIALOG_SHOWN:
        assert step.advance_dialog is not None
        dialogs[step.advance_dialog].show()
    elif step.advance is AdvanceTrigger.DIALOG_HIDDEN:
        assert step.advance_dialog is not None
        dialogs[step.advance_dialog].hide()


def test_unmet_prerequisite_soft_blocks_chapter_on_the_real_window(qtbot, monkeypatch) -> None:
    """Real project-state predicates block a chapter and surface the warning bubble."""
    monkeypatch.setenv("CHAPPY_DOC_AUTO_DISCARD", "1")
    window, preset_store, atomic_data = _prepare_window(qtbot)
    _load_sample_with_one_region(window)
    # The default preset store may carry custom presets persisted by earlier
    # real runs on this machine; pin the predicate to keep the walk deterministic.
    monkeypatch.setattr(MainWindow, "_has_editable_tutorial_preset", lambda _self: False)
    # The walk fakes dialog transitions instead of editing a preset, so the
    # step gates those transitions now respect are stubbed open.
    monkeypatch.setattr(
        MainWindow,
        "_tutorial_completion_checks",
        lambda _self: dict.fromkeys(TutorialCompletion, lambda: True),
    )

    checks = window._tutorial_prerequisite_checks()
    assert checks[TutorialPrerequisite.HAS_CONFIRMED_REGION]()
    assert not checks[TutorialPrerequisite.HAS_TWO_REGIONS]()
    assert not checks[TutorialPrerequisite.HAS_CUSTOM_PRESET]()
    assert not checks[TutorialPrerequisite.HAS_MULTI_ION_REGION]()

    preset_dialog = PresetListDialog(window, preset_store, atomic_data=atomic_data)
    line_dialog = LineSelectionDialog(preset_dialog, atomic_data=atomic_data)
    dialogs = {"presetListDialog": preset_dialog, "spectralDatabaseDialog": line_dialog}

    window.start_tutorial_full_walkthrough()
    controller = window._tutorial_tour
    assert controller is not None
    for _ in range(_MAX_WALK_ACTIONS):
        if not controller.is_active or controller._awaiting_prerequisite:
            break
        QApplication.processEvents()
        step = controller._current_step()
        if step.advance is AdvanceTrigger.NEXT_BUTTON:
            controller._advance()
        elif step.advance is AdvanceTrigger.MODE_CHANGE:
            assert step.advance_mode is not None
            window.switch_mode(step.advance_mode)
        elif step.advance is AdvanceTrigger.DIALOG_SHOWN:
            assert step.advance_dialog is not None
            dialogs[step.advance_dialog].show()
        else:
            assert step.advance_dialog is not None
            dialogs[step.advance_dialog].hide()
        QApplication.processEvents()

    assert controller.is_active
    assert controller._awaiting_prerequisite
    assert controller._current_chapter().chapter_id == "velocity_identify"
    assert controller._bubble is not None
    assert "none has been created yet" in controller._bubble._action_label.text()
    controller.stop()


def test_full_walkthrough_destinations_apply_and_all_targets_resolve(
    qtbot, caplog, monkeypatch
) -> None:
    """Walking every chapter in order resolves each step without target misses."""
    # Without auto-discard, closing the dirtied window at teardown blocks on
    # the modal save prompt and hangs the headless run.
    monkeypatch.setenv("CHAPPY_DOC_AUTO_DISCARD", "1")
    # This walk emulates dialog/mode transitions without real data edits, so
    # later chapters' prerequisites are satisfied by stubbing the predicates.
    monkeypatch.setattr(
        MainWindow,
        "_tutorial_prerequisite_checks",
        lambda _self: dict.fromkeys(TutorialPrerequisite, lambda: True),
    )
    monkeypatch.setattr(
        MainWindow,
        "_tutorial_completion_checks",
        lambda _self: dict.fromkeys(TutorialCompletion, lambda: True),
    )
    window, preset_store, atomic_data = _prepare_window(qtbot)
    _load_sample_with_one_region(window)

    preset_dialog = PresetListDialog(window, preset_store, atomic_data=atomic_data)
    line_dialog = LineSelectionDialog(preset_dialog, atomic_data=atomic_data)
    dialogs = {"presetListDialog": preset_dialog, "spectralDatabaseDialog": line_dialog}
    velocity_overlay = SpectrumVelocityOverlayWidget(window)
    velocity_overlay.show()

    with caplog.at_level(logging.WARNING, logger=_TOUR_LOGGER):
        window.start_tutorial_full_walkthrough()
        controller = window._tutorial_tour
        assert controller is not None
        assert controller.is_active

        visited: list[tuple[str, int]] = []
        for _ in range(_MAX_WALK_ACTIONS):
            if not controller.is_active:
                break
            QApplication.processEvents()
            chapter = controller._current_chapter()
            step = controller._current_step()
            position = (chapter.chapter_id, controller._step_index)
            assert position not in visited, f"walk revisited {position}"
            visited.append(position)
            _apply_step_advance(window, controller, step, dialogs)
            QApplication.processEvents()
        else:
            pytest.fail("walkthrough did not finish within the action budget")

    assert not controller.is_active

    expected_chapters = [chapter.chapter_id for chapter in build_full_walkthrough_chapters()]
    walked_chapters = list(dict.fromkeys(chapter_id for chapter_id, _ in visited))
    assert walked_chapters == expected_chapters

    expected_step_count = sum(len(chapter.steps) for chapter in build_full_walkthrough_chapters())
    assert len(visited) == expected_step_count

    not_found = [
        record.getMessage()
        for record in caplog.records
        if "Tutorial target widget not found" in record.getMessage()
    ]
    assert not_found == []
    skipped = [
        record.getMessage()
        for record in caplog.records
        if "Tutorial chapter skipped" in record.getMessage()
    ]
    assert skipped == []
    spanned = [
        record.getMessage()
        for record in caplog.records
        if "span multiple windows" in record.getMessage()
    ]
    assert spanned == []


def test_no_interact_target_resolves_to_a_dialog_button_box(qtbot, monkeypatch) -> None:
    """An INTERACT target names the control the user operates, never its footer container."""
    monkeypatch.setenv("CHAPPY_DOC_AUTO_DISCARD", "1")
    monkeypatch.setattr(
        MainWindow,
        "_tutorial_prerequisite_checks",
        lambda _self: dict.fromkeys(TutorialPrerequisite, lambda: True),
    )
    monkeypatch.setattr(
        MainWindow,
        "_tutorial_completion_checks",
        lambda _self: dict.fromkeys(TutorialCompletion, lambda: True),
    )
    window, preset_store, atomic_data = _prepare_window(qtbot)
    _load_sample_with_one_region(window)

    preset_dialog = PresetListDialog(window, preset_store, atomic_data=atomic_data)
    line_dialog = LineSelectionDialog(preset_dialog, atomic_data=atomic_data)
    dialogs = {"presetListDialog": preset_dialog, "spectralDatabaseDialog": line_dialog}
    velocity_overlay = SpectrumVelocityOverlayWidget(window)
    velocity_overlay.show()

    window.start_tutorial_full_walkthrough()
    controller = window._tutorial_tour
    assert controller is not None

    checked: set[str] = set()
    for _ in range(_MAX_WALK_ACTIONS):
        if not controller.is_active:
            break
        QApplication.processEvents()
        step = controller._current_step()
        for target in step.targets:
            if target.role is not TutorialTargetRole.INTERACT:
                continue
            widget = controller._resolve_target(target)
            assert widget is not None, target.object_name
            assert not isinstance(widget, QDialogButtonBox), (
                f"{target.object_name} spotlights a button-box container,"
                " not the control to operate"
            )
            checked.add(target.object_name)
        _apply_step_advance(window, controller, step, dialogs)
        QApplication.processEvents()
    else:
        pytest.fail("walkthrough did not finish within the action budget")

    declared = {
        target.object_name
        for chapter in build_full_walkthrough_chapters()
        for chapter_step in chapter.steps
        for target in chapter_step.targets
        if target.role is TutorialTargetRole.INTERACT
    }
    assert checked == declared
