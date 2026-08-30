"""Spotlight overlay and coach-mark bubble for the guided tour.

The spotlight layer blocks mouse input except over targets explicitly marked
for interaction; the separately raised bubble keeps accepting input.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QT_TRANSLATE_NOOP,
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPainterPath, QPen, QRegion, QShowEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

from chappy.gui.common.tutorial.model import (
    TUTORIAL_TR_CONTEXT,
    TutorialTargetProminence,
    TutorialTargetRole,
)
from chappy.gui.dialog_sizing import fit_height_to_width
from chappy.gui.theme import Colors, apply_button_variant

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from chappy.gui.common.tutorial.model import TutorialStep

_DIM_COLOR = QColor(0, 0, 0, 150)
_SPOTLIGHT_MARGIN = 6
_SPOTLIGHT_RADIUS = 6.0
_GEOMETRY_POLL_INTERVAL_MS = 200
_BUBBLE_GAP = 12
_BUBBLE_WIDTH = 380
_PRIMARY_OUTLINE_WIDTH = 2
_RELATED_OUTLINE_WIDTH = 1

_EXIT_TOUR_SOURCE = str(QT_TRANSLATE_NOOP("Tutorial", "Exit Tour"))
_BACK_SOURCE = str(QT_TRANSLATE_NOOP("Tutorial", "Back"))
_NEXT_SOURCE = str(QT_TRANSLATE_NOOP("Tutorial", "Next"))
_CONTINUE_ANYWAY_SOURCE = str(QT_TRANSLATE_NOOP("Tutorial", "Continue anyway"))
_NOTE_TOGGLE_SOURCE = str(QT_TRANSLATE_NOOP("Tutorial", "What is this?"))


def _translate(source: str) -> str:
    return QCoreApplication.translate(TUTORIAL_TR_CONTEXT, source)


def _identity_text(text: str) -> str:
    """Return text unchanged when no runtime formatter is injected."""
    return text


def _intersection_area(first: QRect, second: QRect) -> int:
    """Return the non-negative intersection area of two rectangles."""
    intersection = first.intersected(second)
    return max(intersection.width(), 0) * max(intersection.height(), 0)


def _visible_target_rect(
    target: QWidget, parent: QWidget, *, margin: int = _SPOTLIGHT_MARGIN
) -> QRect | None:
    """Return the target portion actually paintable through scroll viewports."""
    if not target.isVisibleTo(parent):
        return None

    target_rect = QRect(target.mapTo(parent, QPoint(0, 0)), target.size())
    clipping_rect = parent.rect()
    ancestor = target.parentWidget()
    while ancestor is not None and ancestor is not parent:
        if isinstance(ancestor, QAbstractScrollArea):
            viewport = ancestor.viewport()
            viewport_rect = QRect(viewport.mapTo(parent, QPoint(0, 0)), viewport.size())
            clipping_rect = clipping_rect.intersected(viewport_rect)
        ancestor = ancestor.parentWidget()

    visible_rect = target_rect.intersected(clipping_rect)
    if visible_rect.isEmpty():
        return None
    return visible_rect.adjusted(-margin, -margin, margin, margin).intersected(clipping_rect)


@dataclass(frozen=True, slots=True)
class TutorialSpotlightTarget:
    """Resolved widget and its semantic role in the current tutorial step."""

    widget: QWidget
    role: TutorialTargetRole
    prominence: TutorialTargetProminence

    def __post_init__(self) -> None:
        """Reject invalid values at the Qt resolution boundary."""
        if not isinstance(self.widget, QWidget):
            msg = "Tutorial spotlight widget must be a QWidget."
            raise TypeError(msg)
        if not isinstance(self.role, TutorialTargetRole):
            msg = "Tutorial spotlight role must be a TutorialTargetRole."
            raise TypeError(msg)
        if not isinstance(self.prominence, TutorialTargetProminence):
            msg = "Tutorial spotlight prominence must be a TutorialTargetProminence."
            raise TypeError(msg)


@dataclass(frozen=True, slots=True)
class _TrackedTarget:
    target: TutorialSpotlightTarget
    key: int
    destroyed_callback: Callable[[QObject | None], None]


@dataclass(frozen=True, slots=True)
class _Spotlight:
    rect: QRect
    role: TutorialTargetRole
    prominence: TutorialTargetProminence


@dataclass(frozen=True, slots=True)
class _ScrollConnection:
    scrollbar: QScrollBar
    callback: Callable[[int], None]


class TutorialSpotlightOverlay(QWidget):
    """Dimming and mouse-input layer with role-aware target cutouts."""

    spotlight_changed = Signal()

    def __init__(self, parent: QWidget) -> None:
        """Initialize the overlay covering the given window.

        Args:
            parent: Top-level window the overlay covers.
        """
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setProperty("doc.include", False)
        self._targets: tuple[_TrackedTarget, ...] = ()
        self._spotlights: tuple[_Spotlight, ...] = ()
        self._geometry_watched_objects: tuple[QObject, ...] = ()
        self._scroll_connections: tuple[_ScrollConnection, ...] = ()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_GEOMETRY_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._sync_spotlight_rect)
        self._geometry_refresh_timer = QTimer(self)
        self._geometry_refresh_timer.setSingleShot(True)
        self._geometry_refresh_timer.timeout.connect(self._refresh_geometry_observers)

        self.setGeometry(parent.rect())

    def set_targets(self, targets: Sequence[TutorialSpotlightTarget]) -> None:
        """Spotlight resolved widgets, or dim uniformly when empty.

        Args:
            targets: Resolved widgets with their tutorial semantics.
        """
        self._close_interaction_holes()
        self._detach_geometry_observers()
        for tracked in self._targets:
            with contextlib.suppress(RuntimeError):
                tracked.target.widget.destroyed.disconnect(tracked.destroyed_callback)

        tracked_targets: list[_TrackedTarget] = []
        for key, target in enumerate(targets):
            callback = partial(self._remove_destroyed_target, key)
            target.widget.destroyed.connect(callback)
            tracked_targets.append(
                _TrackedTarget(target=target, key=key, destroyed_callback=callback)
            )
        self._targets = tuple(tracked_targets)
        self._attach_geometry_observers()
        self._sync_spotlight_rect()

    def _remove_destroyed_target(self, key: int, _destroyed: QObject | None = None) -> None:
        self._close_interaction_holes()
        self._detach_geometry_observers()
        self._targets = tuple(tracked for tracked in self._targets if tracked.key != key)
        self._attach_geometry_observers()
        self._sync_spotlight_rect()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Start geometry tracking while visible."""
        self._poll_timer.start()
        super().showEvent(event)
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self._attach_geometry_observers()
        self._sync_spotlight_rect()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        """Stop geometry tracking and remove the input mask when hidden."""
        self._poll_timer.stop()
        self._geometry_refresh_timer.stop()
        self._detach_geometry_observers()
        self.clearMask()
        super().hideEvent(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Synchronize input holes before geometry changes can expose stale targets."""
        if watched is self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            parent = self.parentWidget()
            if parent is not None:
                self.setGeometry(parent.rect())
            self._sync_spotlight_rect()
            return super().eventFilter(watched, event)

        if event.type() in (QEvent.Type.Hide, QEvent.Type.ParentAboutToChange):
            self._close_interaction_holes()
            self._schedule_geometry_refresh()
        elif event.type() == QEvent.Type.ParentChange:
            self._refresh_geometry_observers()
        elif event.type() in (
            QEvent.Type.Show,
            QEvent.Type.Move,
            QEvent.Type.Resize,
            QEvent.Type.LayoutRequest,
        ):
            self._sync_spotlight_rect()
        return super().eventFilter(watched, event)

    def paintEvent(self, _event: QEvent) -> None:  # noqa: N802 - Qt API
        """Paint the dim layer with rounded cutouts over all visible targets."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dim_path = QPainterPath()
        dim_path.addRect(self.rect())
        for spotlight in self._spotlights:
            cutout = QPainterPath()
            cutout.addRoundedRect(spotlight.rect, _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)
            dim_path = dim_path.subtracted(cutout)
        painter.fillPath(dim_path, _DIM_COLOR)

        for spotlight in self._spotlights:
            color = QColor(
                {
                    TutorialTargetRole.INTERACT: Colors.PRIMARY,
                    TutorialTargetRole.OBSERVE: Colors.SUCCESS,
                    TutorialTargetRole.CONTEXT: Colors.SECONDARY,
                }[spotlight.role]
            )
            width = (
                _PRIMARY_OUTLINE_WIDTH
                if spotlight.prominence is TutorialTargetProminence.PRIMARY
                else _RELATED_OUTLINE_WIDTH
            )
            painter.setPen(QPen(color, width))
            painter.drawRoundedRect(spotlight.rect, _SPOTLIGHT_RADIUS, _SPOTLIGHT_RADIUS)

    def event(self, event: QEvent) -> bool:
        """Consume mouse input delivered to the blocking portion of the overlay."""
        if event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
            QEvent.Type.ContextMenu,
        ):
            event.accept()
            return True
        return super().event(event)

    def spotlight_rects(self) -> tuple[QRect, ...]:
        """Return all current cutout rectangles in overlay coordinates."""
        return tuple(spotlight.rect for spotlight in self._spotlights)

    def primary_spotlight_rect(self) -> QRect | None:
        """Return the visible primary cutout used as the bubble anchor.

        Returns:
            Primary spotlight rectangle, or None when it is not visible.
        """
        return next(
            (
                spotlight.rect
                for spotlight in self._spotlights
                if spotlight.prominence is TutorialTargetProminence.PRIMARY
            ),
            None,
        )

    def _attach_geometry_observers(self) -> None:
        if not self.isVisible() or self._geometry_watched_objects:
            return

        watched_by_identity: dict[int, QObject] = {}
        scrollbars_by_identity: dict[int, QScrollBar] = {}
        parent = self.parentWidget()
        if parent is not None:
            watched_by_identity[id(parent)] = parent
        for tracked in self._targets:
            ancestor: QWidget | None = tracked.target.widget
            while ancestor is not None:
                watched_by_identity[id(ancestor)] = ancestor
                if isinstance(ancestor, QAbstractScrollArea):
                    for scrollbar in (
                        ancestor.horizontalScrollBar(),
                        ancestor.verticalScrollBar(),
                    ):
                        scrollbars_by_identity[id(scrollbar)] = scrollbar
                if ancestor is parent:
                    break
                ancestor = ancestor.parentWidget()

        watched_objects = tuple(watched_by_identity.values())
        for watched in watched_objects:
            watched.installEventFilter(self)
        self._geometry_watched_objects = watched_objects

        connections: list[_ScrollConnection] = []
        for scrollbar in scrollbars_by_identity.values():
            callback = self._handle_scroll_value_changed
            scrollbar.valueChanged.connect(callback)
            connections.append(_ScrollConnection(scrollbar=scrollbar, callback=callback))
        self._scroll_connections = tuple(connections)

    def _detach_geometry_observers(self) -> None:
        for connection in self._scroll_connections:
            with contextlib.suppress(RuntimeError):
                connection.scrollbar.valueChanged.disconnect(connection.callback)
        self._scroll_connections = ()
        for watched in self._geometry_watched_objects:
            with contextlib.suppress(RuntimeError):
                watched.removeEventFilter(self)
        self._geometry_watched_objects = ()

    def _handle_scroll_value_changed(self, _value: int) -> None:
        self._sync_spotlight_rect()

    def _close_interaction_holes(self) -> None:
        if self.isVisible():
            self.setMask(QRegion(self.rect()))

    def _schedule_geometry_refresh(self) -> None:
        if not self._geometry_refresh_timer.isActive():
            self._geometry_refresh_timer.start(0)

    def _refresh_geometry_observers(self) -> None:
        try:
            self._geometry_refresh_timer.stop()
            self._detach_geometry_observers()
            self._attach_geometry_observers()
            self._sync_spotlight_rect()
        except RuntimeError:
            return

    def _sync_spotlight_rect(self) -> None:
        parent = self.parentWidget()
        spotlights: list[_Spotlight] = []
        interactive_region = QRegion()
        if parent is not None:
            for tracked in self._targets:
                target = tracked.target.widget
                rect = _visible_target_rect(target, parent)
                if rect is None:
                    continue
                spotlights.append(
                    _Spotlight(
                        rect=rect, role=tracked.target.role, prominence=tracked.target.prominence
                    )
                )
                if tracked.target.role is TutorialTargetRole.INTERACT:
                    interactive_rect = _visible_target_rect(target, parent, margin=0)
                    if interactive_rect is not None:
                        interactive_region += QRegion(interactive_rect)
        new_spotlights = tuple(spotlights)
        if new_spotlights != self._spotlights:
            self._spotlights = new_spotlights
            self.update()
            self.spotlight_changed.emit()
        targets_hidden = (
            parent is not None
            and self._targets
            and not any(tracked.target.widget.isVisibleTo(parent) for tracked in self._targets)
        )
        if self.isVisible() and parent is not None and targets_hidden:
            # A target can disappear mid-step (for example, closing the velocity
            # plot from inside its own interaction target). An empty widget mask
            # keeps the host usable until the tracked target becomes visible again.
            self.setMask(QRegion())
        elif self.isVisible() and parent is not None:
            self.setMask(QRegion(self.rect()).subtracted(interactive_region))
        else:
            self.clearMask()


class TutorialBubble(QFrame):
    """Interactive coach-mark panel showing one step's texts and controls."""

    next_requested = Signal()
    back_requested = Signal()
    close_requested = Signal()

    def __init__(
        self, parent: QWidget, *, text_formatter: Callable[[str], str] | None = None
    ) -> None:
        """Initialize the bubble.

        Args:
            parent: Top-level window the bubble floats over.
            text_formatter: Optional post-translation formatter for runtime values.
        """
        super().__init__(parent)
        self.setObjectName("tutorialBubble")
        self.setProperty("doc.include", False)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        self.setFixedWidth(_BUBBLE_WIDTH)

        self._step: TutorialStep | None = None
        self._progress_text = ""
        self._chapter_title_source: str | None = None
        self._checkpoint_source: str | None = None
        self._warning_source: str | None = None
        self._note_expanded = False
        self._completion_met = False
        self._completion_note: str | None = None
        self._text_formatter = text_formatter or _identity_text

        self._build_ui()
        self._wire_signals()
        self._retranslate_ui()

    def show_step(
        self,
        step: TutorialStep,
        *,
        chapter_title_source: str,
        progress_text: str,
        checkpoint_source: str | None = None,
        completion_met: bool = False,
        completion_note: str | None = None,
    ) -> None:
        """Render the given step.

        Args:
            step: Step to display.
            chapter_title_source: Untranslated chapter title.
            progress_text: Pre-formatted progress indicator (e.g. "2/5").
            checkpoint_source: Untranslated checkpoint question shown below
                this step's text.
            completion_met: Whether a gated step's completion condition
                currently holds; ignored when ``step.requires`` is None.
            completion_note: Optional already-translated note explaining a
                gated step's completion state, shown under the expected line.
        """
        self._step = step
        self._chapter_title_source = chapter_title_source
        self._progress_text = progress_text
        self._checkpoint_source = checkpoint_source
        self._warning_source = None
        self._note_expanded = False
        self._completion_met = completion_met
        self._completion_note = completion_note
        self._retranslate_ui()
        fit_height_to_width(self)

    def show_prerequisite_warning(self, *, chapter_title_source: str, warning_source: str) -> None:
        """Render a soft-block warning offering [Back] and [Continue anyway].

        Args:
            chapter_title_source: Untranslated title of the blocked chapter.
            warning_source: Untranslated explanation of the unmet prerequisite.
        """
        self._step = None
        self._chapter_title_source = chapter_title_source
        self._progress_text = ""
        self._checkpoint_source = None
        self._warning_source = warning_source
        self._note_expanded = False
        self._completion_met = False
        self._completion_note = None
        self._retranslate_ui()
        fit_height_to_width(self)

    def set_completion_state(self, *, met: bool, note: str | None) -> None:
        """Update a gated step's completion indicator without resetting note expansion.

        Args:
            met: Whether the step's completion condition currently holds.
            note: Optional already-translated note explaining the state.
        """
        self._completion_met = met
        self._completion_note = note
        self._retranslate_ui()
        fit_height_to_width(self)

    def set_next_enabled(self, enabled: bool) -> None:
        """Enable or disable the next button (disabled while waiting on a signal).

        Args:
            enabled: Whether the next button accepts clicks.
        """
        self._next_button.setEnabled(enabled)

    def set_back_enabled(self, enabled: bool) -> None:
        """Enable or disable the back button (disabled on the tour's first step).

        Args:
            enabled: Whether the back button accepts clicks.
        """
        self._back_button.setEnabled(enabled)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Retranslate on language change."""
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate_ui()
        super().changeEvent(event)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self._title_label = QLabel(self)
        self._title_label.setObjectName("tutorialBubbleTitle")
        self._title_label.setStyleSheet("font-weight: bold;")
        self._progress_label = QLabel(self)
        self._progress_label.setObjectName("tutorialBubbleProgress")
        header.addWidget(self._title_label)
        header.addStretch()
        header.addWidget(self._progress_label)
        layout.addLayout(header)

        self._action_label = QLabel(self)
        self._action_label.setWordWrap(True)
        self._action_label.setObjectName("tutorialBubbleAction")
        layout.addWidget(self._action_label)

        self._expected_label = QLabel(self)
        self._expected_label.setWordWrap(True)
        self._expected_label.setObjectName("tutorialBubbleExpected")
        self._expected_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(self._expected_label)

        self._completion_note_label = QLabel(self)
        self._completion_note_label.setWordWrap(True)
        self._completion_note_label.setObjectName("tutorialBubbleCompletionNote")
        self._completion_note_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        self._completion_note_label.setVisible(False)
        layout.addWidget(self._completion_note_label)

        self._note_toggle = QPushButton(self)
        self._note_toggle.setObjectName("tutorialBubbleNoteToggle")
        self._note_toggle.setFlat(True)
        apply_button_variant(self._note_toggle, "text")
        layout.addWidget(self._note_toggle)

        self._note_label = QLabel(self)
        self._note_label.setWordWrap(True)
        self._note_label.setObjectName("tutorialBubbleNote")
        self._note_label.setVisible(False)
        layout.addWidget(self._note_label)

        self._checkpoint_label = QLabel(self)
        self._checkpoint_label.setWordWrap(True)
        self._checkpoint_label.setObjectName("tutorialBubbleCheckpoint")
        self._checkpoint_label.setStyleSheet("font-weight: bold;")
        self._checkpoint_label.setVisible(False)
        layout.addWidget(self._checkpoint_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self._close_button = QPushButton(self)
        apply_button_variant(self._close_button, "secondary")
        self._back_button = QPushButton(self)
        self._back_button.setObjectName("tutorialBubbleBackButton")
        apply_button_variant(self._back_button, "secondary")
        self._next_button = QPushButton(self)
        apply_button_variant(self._next_button, "primary")
        self._next_button.setDefault(True)
        buttons.addWidget(self._close_button)
        buttons.addStretch()
        buttons.addWidget(self._back_button)
        buttons.addWidget(self._next_button)
        layout.addLayout(buttons)

    def _wire_signals(self) -> None:
        self._close_button.clicked.connect(self.close_requested.emit)
        self._back_button.clicked.connect(self.back_requested.emit)
        self._next_button.clicked.connect(self.next_requested.emit)
        self._note_toggle.clicked.connect(self._toggle_note)

    def _toggle_note(self) -> None:
        self._note_expanded = not self._note_expanded
        self._note_label.setVisible(self._note_expanded)
        fit_height_to_width(self)

    def _retranslate_ui(self) -> None:
        self._close_button.setText(self._translated_text(_EXIT_TOUR_SOURCE))
        self._back_button.setText(self._translated_text(_BACK_SOURCE))
        self._next_button.setText(
            self._translated_text(
                _NEXT_SOURCE if self._warning_source is None else _CONTINUE_ANYWAY_SOURCE
            )
        )
        self._note_toggle.setText(self._translated_text(_NOTE_TOGGLE_SOURCE))
        self._progress_label.setText(self._progress_text)

        if self._chapter_title_source is not None:
            self._title_label.setText(self._translated_text(self._chapter_title_source))
        if self._warning_source is not None:
            self._action_label.setText(self._translated_text(self._warning_source))
            self._expected_label.setVisible(False)
            self._completion_note_label.setVisible(False)
            self._note_toggle.setVisible(False)
            self._note_label.setVisible(False)
            self._checkpoint_label.setVisible(False)
            return
        step = self._step
        if step is None:
            return
        self._action_label.setText(self._translated_text(step.action_source))
        is_gated = step.requires is not None
        expected_text = self._translated_text(step.expected_source)
        if is_gated and self._completion_met:
            self._expected_label.setText(f"✓ {expected_text}")
            self._expected_label.setStyleSheet(f"color: {Colors.SUCCESS};")
        else:
            self._expected_label.setText(expected_text)
            self._expected_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        self._expected_label.setVisible(True)
        has_completion_note = is_gated and self._completion_note is not None
        if has_completion_note and self._completion_note is not None:
            self._completion_note_label.setText(self._completion_note)
        self._completion_note_label.setVisible(has_completion_note)
        has_note = step.domain_note_source is not None
        self._note_toggle.setVisible(has_note)
        if step.domain_note_source is not None:
            self._note_label.setText(self._translated_text(step.domain_note_source))
        self._note_label.setVisible(has_note and self._note_expanded)
        has_checkpoint = self._checkpoint_source is not None
        if self._checkpoint_source is not None:
            self._checkpoint_label.setText(self._translated_text(self._checkpoint_source))
        self._checkpoint_label.setVisible(has_checkpoint)

    def _translated_text(self, source: str) -> str:
        """Translate one static source and then apply injected runtime values."""
        return self._text_formatter(_translate(source))

    def place_near(self, primary_rect: QRect | None, *, avoid_rects: Sequence[QRect] = ()) -> None:
        """Position the bubble near the primary spotlight without hiding cutouts.

        Args:
            primary_rect: Primary spotlight rectangle in parent coordinates.
            avoid_rects: Every cutout rectangle the bubble should avoid.
        """
        parent = self.parentWidget()
        if parent is None:
            return
        fit_height_to_width(self)
        area = parent.rect()
        size = self.size()
        max_x = max(area.width() - size.width(), 0)
        max_y = max(area.height() - size.height(), 0)
        if primary_rect is None and not avoid_rects:
            self.move(max_x // 2, max_y // 2)
            return

        obstacle_rects = tuple(avoid_rects)
        if not obstacle_rects and primary_rect is not None:
            obstacle_rects = (primary_rect,)
        placement_anchor = primary_rect or obstacle_rects[0]
        candidate_x = {
            0,
            max_x,
            min(max(placement_anchor.left(), 0), max_x),
            min(max(placement_anchor.center().x() - size.width() // 2, 0), max_x),
            min(max(placement_anchor.right() - size.width(), 0), max_x),
        }
        candidate_y = {
            0,
            max_y,
            min(max(placement_anchor.top(), 0), max_y),
            min(max(placement_anchor.center().y() - size.height() // 2, 0), max_y),
            min(max(placement_anchor.bottom() - size.height(), 0), max_y),
        }
        for rect in obstacle_rects:
            candidate_x.update(
                {
                    min(max(rect.left() - _BUBBLE_GAP - size.width(), 0), max_x),
                    min(max(rect.right() + _BUBBLE_GAP, 0), max_x),
                }
            )
            candidate_y.update(
                {
                    min(max(rect.top() - _BUBBLE_GAP - size.height(), 0), max_y),
                    min(max(rect.bottom() + _BUBBLE_GAP, 0), max_y),
                }
            )

        anchor = placement_anchor.center()
        candidates = [
            QRect(x, y, size.width(), size.height()) for x in candidate_x for y in candidate_y
        ]
        candidates.sort(
            key=lambda candidate: (
                (_intersection_area(candidate, primary_rect) if primary_rect is not None else 0),
                sum(_intersection_area(candidate, rect) for rect in obstacle_rects),
                abs(candidate.center().x() - anchor.x())
                + abs(candidate.center().y() - anchor.y()),
            )
        )
        best = candidates[0]
        self.move(best.topLeft())
