"""Rendering tests for the tutorial spotlight overlay and bubble placement."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QPushButton, QScrollArea, QWidget

from chappy.gui.common.tutorial import TutorialBubble, TutorialSpotlightOverlay
from chappy.gui.common.tutorial import (
    TutorialSpotlightTarget,
    TutorialStep,
    TutorialTargetProminence,
    TutorialTargetRole,
)

from tests.gui.support.faithful_env import faithful_application_environment

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot


def _target(
    widget: QWidget,
    *,
    role: TutorialTargetRole = TutorialTargetRole.INTERACT,
    prominence: TutorialTargetProminence = TutorialTargetProminence.PRIMARY,
) -> TutorialSpotlightTarget:
    return TutorialSpotlightTarget(widget=widget, role=role, prominence=prominence)


def _click_at_widget_center(widget: QWidget, qtbot: QtBot) -> QWidget:
    """Dispatch a click through Qt's real topmost-widget hit test."""
    return _click_at_global_position(widget.mapToGlobal(widget.rect().center()), qtbot)


def _click_at_global_position(global_position: QPoint, qtbot: QtBot) -> QWidget:
    """Dispatch a click at a fixed global position through Qt hit testing."""
    receiver = QApplication.widgetAt(global_position)
    assert receiver is not None
    qtbot.mouseClick(
        receiver, Qt.MouseButton.LeftButton, pos=receiver.mapFromGlobal(global_position)
    )
    return receiver


@pytest.mark.parametrize("role", [TutorialTargetRole.OBSERVE, TutorialTargetRole.CONTEXT])
def test_non_interactive_spotlight_blocks_target_click(
    qtbot: QtBot, role: TutorialTargetRole
) -> None:
    """Bright observation/context cutouts must not expose the real widget."""
    window = QWidget()
    window.resize(400, 260)
    qtbot.addWidget(window)
    target = QPushButton("Target", window)
    target.setGeometry(80, 70, 120, 40)
    window.show()
    qtbot.waitExposed(window)
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target, role=role),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()

    with qtbot.assertNotEmitted(target.clicked):
        receiver = _click_at_widget_center(target, qtbot)

    assert receiver is overlay


def test_dimmed_area_blocks_unrelated_widget_click(qtbot: QtBot) -> None:
    """The overlay itself must consume clicks outside every INTERACT target."""
    window = QWidget()
    window.resize(400, 260)
    qtbot.addWidget(window)
    target = QPushButton("Target", window)
    target.setGeometry(40, 60, 100, 40)
    unrelated = QPushButton("Unrelated", window)
    unrelated.setGeometry(240, 160, 100, 40)
    window.show()
    qtbot.waitExposed(window)
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()

    with qtbot.assertNotEmitted(unrelated.clicked):
        receiver = _click_at_widget_center(unrelated, qtbot)

    assert receiver is overlay


def test_interactive_spotlight_passes_click_to_real_widget(qtbot: QtBot) -> None:
    """Only an INTERACT target's actual visible widget area is click-through."""
    window = QWidget()
    window.resize(400, 260)
    qtbot.addWidget(window)
    target = QPushButton("Target", window)
    target.setGeometry(80, 70, 120, 40)
    window.show()
    qtbot.waitExposed(window)
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()

    with qtbot.waitSignal(target.clicked):
        receiver = _click_at_widget_center(target, qtbot)

    assert receiver is target


def test_hiding_overlay_removes_click_blocking(qtbot: QtBot) -> None:
    """Ending a step must not leave an input mask over the application."""
    window = QWidget()
    window.resize(400, 260)
    qtbot.addWidget(window)
    target = QPushButton("Target", window)
    target.setGeometry(80, 70, 120, 40)
    window.show()
    qtbot.waitExposed(window)
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target, role=TutorialTargetRole.OBSERVE),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()
    overlay.hide()
    QApplication.processEvents()

    with qtbot.waitSignal(target.clicked):
        receiver = _click_at_widget_center(target, qtbot)

    assert receiver is target
    assert overlay.mask().isEmpty()
    assert overlay._geometry_watched_objects == ()
    assert overlay._scroll_connections == ()


def test_destroyed_target_clears_spotlight_without_error(qtbot: QtBot) -> None:
    """Deleting the spotlighted widget must not leave a dangling reference."""
    window = QWidget()
    window.resize(400, 300)
    qtbot.addWidget(window)
    target = QWidget(window)
    target.setGeometry(50, 50, 100, 40)
    window.show()
    qtbot.waitExposed(window)

    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target),))
    overlay.show()
    assert overlay.primary_spotlight_rect() is not None

    target.setParent(None)
    target.deleteLater()
    qtbot.wait(10)

    overlay._sync_spotlight_rect()
    assert overlay.primary_spotlight_rect() is None
    assert overlay.spotlight_rects() == ()


def test_multiple_targets_create_multiple_cutouts_and_primary_anchor(qtbot: QtBot) -> None:
    """Every visible target is cut out while only PRIMARY anchors the bubble."""
    window = QWidget()
    window.resize(500, 300)
    qtbot.addWidget(window)
    primary = QWidget(window)
    primary.setGeometry(40, 50, 80, 40)
    related = QWidget(window)
    related.setGeometry(300, 180, 100, 50)
    window.show()
    qtbot.waitExposed(window)

    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets(
        (_target(primary), _target(related, prominence=TutorialTargetProminence.RELATED))
    )

    rects = overlay.spotlight_rects()
    assert len(rects) == 2
    assert overlay.primary_spotlight_rect() == rects[0]
    assert rects[0].center().x() < rects[1].center().x()


def test_hidden_target_is_removed_from_cutouts_until_visible(qtbot: QtBot) -> None:
    """Hiding an INTERACT target must close its old hole before another click."""
    window = QWidget()
    window.resize(500, 300)
    qtbot.addWidget(window)
    target = QPushButton("Target", window)
    target.setGeometry(40, 50, 80, 40)
    window.show()
    qtbot.waitExposed(window)
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()
    assert len(overlay.spotlight_rects()) == 1
    target_center = target.mapTo(window, target.rect().center())
    target_global_center = target.mapToGlobal(target.rect().center())
    assert not overlay.mask().contains(target_center)

    target.hide()
    assert overlay.mask().contains(target_center)
    with qtbot.assertNotEmitted(target.clicked):
        receiver = _click_at_global_position(target_global_center, qtbot)
    assert receiver is overlay

    target.show()
    assert len(overlay.spotlight_rects()) == 1
    assert not overlay.mask().contains(target_center)
    with qtbot.waitSignal(target.clicked):
        receiver = _click_at_widget_center(target, qtbot)
    assert receiver is target


def test_scroll_change_immediately_moves_interactive_hole(qtbot: QtBot) -> None:
    """A scrollbar signal must close the old hole and expose only the new target position."""
    window = QWidget()
    window.resize(360, 240)
    qtbot.addWidget(window)
    scroll = QScrollArea(window)
    scroll.setGeometry(20, 20, 220, 150)
    content = QWidget()
    content.resize(200, 400)
    target = QPushButton("Target", content)
    target.setGeometry(30, 90, 120, 40)
    scroll.setWidget(content)
    window.show()
    qtbot.waitExposed(window)
    QApplication.processEvents()
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()
    old_center = target.mapTo(window, target.rect().center())

    scroll.verticalScrollBar().setValue(70)
    new_center = target.mapTo(window, target.rect().center())

    assert old_center != new_center
    assert overlay.mask().contains(old_center)
    assert not overlay.mask().contains(new_center)
    with qtbot.assertNotEmitted(target.clicked):
        old_receiver = _click_at_global_position(window.mapToGlobal(old_center), qtbot)
    assert old_receiver is overlay
    with qtbot.waitSignal(target.clicked):
        new_receiver = _click_at_widget_center(target, qtbot)
    assert new_receiver is target


def test_replacing_target_closes_old_hole_without_leaking_observers(qtbot: QtBot) -> None:
    """Replacing targets must detach old tracking and expose only the new INTERACT widget."""
    window = QWidget()
    window.resize(500, 300)
    qtbot.addWidget(window)
    old_target = QPushButton("Old", window)
    old_target.setGeometry(40, 50, 100, 40)
    new_target = QPushButton("New", window)
    new_target.setGeometry(300, 180, 100, 40)
    window.show()
    qtbot.waitExposed(window)
    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(old_target),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()

    overlay.set_targets((_target(new_target),))

    assert old_target not in overlay._geometry_watched_objects
    assert new_target in overlay._geometry_watched_objects
    with qtbot.assertNotEmitted(old_target.clicked):
        old_receiver = _click_at_widget_center(old_target, qtbot)
    assert old_receiver is overlay
    with qtbot.waitSignal(new_target.clicked):
        new_receiver = _click_at_widget_center(new_target, qtbot)
    assert new_receiver is new_target

    old_target.move(200, 40)
    assert overlay.primary_spotlight_rect() is not None
    assert overlay.primary_spotlight_rect().contains(
        new_target.mapTo(window, new_target.rect().center())
    )


def test_target_outside_scroll_viewport_has_no_cutout(qtbot: QtBot) -> None:
    """Qt logical visibility must not create a cutout outside the viewport."""
    window = QWidget()
    window.resize(320, 220)
    qtbot.addWidget(window)
    scroll = QScrollArea(window)
    scroll.setGeometry(20, 20, 200, 150)
    content = QWidget()
    content.resize(180, 600)
    target = QWidget(content)
    target.setGeometry(20, 520, 120, 40)
    scroll.setWidget(content)
    window.show()
    qtbot.waitExposed(window)
    QApplication.processEvents()
    assert target.isVisibleTo(window)

    overlay = TutorialSpotlightOverlay(window)
    overlay.set_targets((_target(target),))
    overlay.show()
    overlay.raise_()
    QApplication.processEvents()
    assert overlay.spotlight_rects() == ()

    scroll.ensureWidgetVisible(target, 8, 8)
    QApplication.processEvents()
    overlay._sync_spotlight_rect()

    spotlight = overlay.primary_spotlight_rect()
    assert spotlight is not None
    viewport = scroll.viewport()
    viewport_rect = QRect(viewport.mapTo(window, QPoint(0, 0)), viewport.size())
    assert viewport_rect.contains(spotlight)
    assert not overlay.mask().contains(target.mapTo(window, target.rect().center()))

    previous_center = target.mapTo(window, target.rect().center())
    scroll.verticalScrollBar().setValue(0)
    QApplication.processEvents()
    overlay._sync_spotlight_rect()
    assert overlay.spotlight_rects() == ()
    assert overlay.mask().contains(previous_center)


def test_bubble_placement_stays_inside_parent(qtbot: QtBot) -> None:
    """The bubble must stay within the window for every spotlight geometry."""
    window = QWidget()
    window.resize(900, 700)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    bubble = TutorialBubble(window)

    spotlights = [
        QRect(10, 10, 120, 40),
        QRect(10, 600, 120, 80),
        QRect(0, 0, 880, 680),
        QRect(-20, -20, 2000, 2000),
    ]
    for rect in spotlights:
        bubble.place_near(rect)
        assert bubble.geometry().left() >= 0
        assert bubble.geometry().top() >= 0
        assert bubble.geometry().right() <= window.width()
        assert bubble.geometry().bottom() <= window.height()

    bubble.place_near(None)
    assert window.rect().contains(bubble.geometry())


def test_bubble_avoids_small_spotlight(qtbot: QtBot) -> None:
    """For a small spotlight the bubble must not cover it."""
    window = QWidget()
    window.resize(900, 700)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    bubble = TutorialBubble(window)

    rect = QRect(200, 200, 150, 40)
    bubble.place_near(rect)
    assert not bubble.geometry().intersects(rect)


def test_bubble_avoids_all_cutouts(qtbot: QtBot) -> None:
    """Related cutouts must be kept visible when positioning from the primary."""
    window = QWidget()
    window.resize(900, 700)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    bubble = TutorialBubble(window)
    primary = QRect(200, 180, 160, 50)
    related = QRect(180, 250, 420, 130)

    bubble.place_near(primary, avoid_rects=(primary, related))

    assert not bubble.geometry().intersects(primary)
    assert not bubble.geometry().intersects(related)


def test_bubble_keeps_primary_clear_when_all_cutouts_cannot_be_avoided(qtbot: QtBot) -> None:
    """A large related region must never displace the bubble onto PRIMARY."""
    window = QWidget()
    window.resize(800, 600)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    bubble = TutorialBubble(window)
    bubble.show_step(
        TutorialStep(
            targets=(),
            action_source=(
                "自動推定を実行すると、スペクトル全体に連続光モデルが表示されます。"
                "モデルと制御点を確認してください。推定結果をスペクトル上で比較し、"
                "曲線の形状が吸収線を追っていないことも確認します。"
            ),
            expected_source=(
                "推定された曲線と制御点一覧を比較し、必要に応じて調整します。"
                "関連する表示領域は広いため、すべてを避けられない場合があります。"
                "確認後は次のステップへ進みます。"
            ),
        ),
        chapter_title_source="連続光を補正する",
        progress_text="2/5",
    )
    assert bubble.sizeHint().height() >= 200
    primary = QRect(650, 520, 130, 50)
    related = QRect(0, 50, 800, 500)

    bubble.place_near(primary, avoid_rects=(primary, related))

    assert bubble.geometry().intersects(related)
    assert not bubble.geometry().intersects(primary)


@pytest.mark.parametrize("language", ["ja", "en"])
def test_bubble_buttons_size_the_same_over_a_window_and_over_a_dialog(
    qtbot: QtBot, language: str
) -> None:
    """The coach mark must render identically whichever window it floats over."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    step = TutorialStep(
        targets=(),
        action_source="Open the observation data dialog.",
        expected_source="The dialog appears.",
        domain_note_source="Absorbers imprint narrow lines on the quasar continuum.",
    )
    renderings: list[tuple[QSize, tuple[QSize, ...]]] = []
    with faithful_application_environment(app, language):
        for host in (QMainWindow(), QDialog()):
            qtbot.addWidget(host)
            host.resize(900, 700)
            host.show()
            qtbot.waitExposed(host)
            bubble = TutorialBubble(host)
            bubble.show_step(step, chapter_title_source="Getting started", progress_text="2/5")
            bubble.show()
            app.processEvents()
            renderings.append(
                (
                    bubble.size(),
                    tuple(button.size() for button in bubble.findChildren(QPushButton)),
                )
            )
            host.close()

    assert renderings[0] == renderings[1]
