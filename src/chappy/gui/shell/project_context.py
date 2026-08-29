"""Typed project context identity for shell-owned UI restoration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from chappy.gui.modes.common.project_key import (
    ProjectKey,
    ProjectPathCanonicalizationError,
    canonical_project_path,
)

if TYPE_CHECKING:
    from chappy.core.spectroscopy_project import SpectroscopyProject


class ProjectContextChangeReason(StrEnum):
    """Reason why the shell replaced or re-keyed its project context."""

    CREATE = "create"
    OPEN = "open"
    SAVE_AS = "save_as"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class ProjectContextChanged:
    """Atomic project/path context published after shell refresh completes."""

    project: SpectroscopyProject | None
    old_key: ProjectKey | None
    new_key: ProjectKey | None
    old_path: str | None
    new_path: str | None
    reason: ProjectContextChangeReason


__all__ = [
    "ProjectContextChangeReason",
    "ProjectContextChanged",
    "ProjectKey",
    "ProjectPathCanonicalizationError",
    "canonical_project_path",
]
