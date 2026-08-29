"""History adapter for continuum point mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from chappy.core.components.continuum import ContinuumComponent
    from chappy.gui.modes.continuum.editor import ContinuumHistoryRecorder


class ContinuumPointHistoryPort(Protocol):
    """History operations required by continuum point mutation workflow."""

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return a scope that restores history state when recording fails."""
        ...

    def record_add_component(self, continuum: ContinuumComponent) -> None:
        """Record a continuum component addition."""
        ...

    def record_add_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point addition."""
        ...

    def record_delete_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point deletion."""
        ...

    def record_move_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point move."""
        ...

    def record_reset(
        self,
        continuum: ContinuumComponent,
        old_points: list[tuple[float, float]],
        new_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point replacement."""
        ...


@dataclass(frozen=True)
class ContinuumHistoryAdapter:
    """Adapt the shell history recorder to continuum mode history operations."""

    recorder_provider: Callable[[], ContinuumHistoryRecorder | None]

    def _require_recorder(self) -> ContinuumHistoryRecorder:
        """Return the production history recorder or fail fast."""
        recorder = self.recorder_provider()
        if recorder is None:
            msg = "Scientific continuum mutations require a connected history recorder."
            raise RuntimeError(msg)
        return recorder

    def atomic_recording(self) -> AbstractContextManager[None]:
        """Return the required production history transaction."""
        return self._require_recorder().atomic_recording()

    def record_add_component(self, continuum: ContinuumComponent) -> None:
        """Record a continuum component addition."""
        self._require_recorder().record_cont_add_component(continuum)

    def record_add_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point addition."""
        self._require_recorder().record_cont_add_point(continuum, before_points, after_points)

    def record_delete_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point deletion."""
        self._require_recorder().record_cont_delete_point(continuum, before_points, after_points)

    def record_move_point(
        self,
        continuum: ContinuumComponent,
        before_points: list[tuple[float, float]],
        after_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point move."""
        self._require_recorder().record_cont_move_point(continuum, before_points, after_points)

    def record_reset(
        self,
        continuum: ContinuumComponent,
        old_points: list[tuple[float, float]],
        new_points: list[tuple[float, float]],
    ) -> None:
        """Record a continuum point replacement."""
        self._require_recorder().record_cont_reset(continuum, old_points, new_points)
