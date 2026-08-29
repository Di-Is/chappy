"""Tests for user-facing Analysis navigation persistence recovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from chappy.gui.modes.common.analysis_navigation import (
    AnalysisNavigationPersistenceIssue,
    AnalysisNavigationPersistenceOperation,
)
from chappy.gui.modes.common.project_key import ProjectKey
from chappy.gui.shell.composition import (
    _analysis_navigation_persistence_status,
    _show_analysis_navigation_persistence_error,
)

if TYPE_CHECKING:
    from chappy.gui.shell.main_window import MainWindow


@dataclass
class _StatusWindow:
    """Capture shell status messages without constructing the complete window."""

    messages: list[tuple[str, int]] = field(default_factory=list)

    def show_status_message(self, message: str, timeout_ms: int) -> None:
        """Record one visible status message."""
        self.messages.append((message, timeout_ms))


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (
            AnalysisNavigationPersistenceOperation.LOAD,
            "Previous Analysis view settings could not be restored. Overview is shown; project data is unchanged.",
        ),
        (
            AnalysisNavigationPersistenceOperation.SAVE,
            "Analysis view settings could not be saved. You can keep working; project data is unchanged, but this view may not be restored next time.",
        ),
        (
            AnalysisNavigationPersistenceOperation.MIGRATE,
            "Analysis view settings could not be saved for the new file. You can keep working; project data is unchanged, but this view may not be restored next time.",
        ),
    ],
)
def test_persistence_status_explains_recovery_without_internal_terms(
    operation: AnalysisNavigationPersistenceOperation, expected: str
) -> None:
    """Each recovery path should state its user-visible consequence directly."""
    status = _analysis_navigation_persistence_status(operation)

    assert status == expected
    assert "QSettings" not in status


def test_persistence_issue_hides_diagnostic_detail_from_status() -> None:
    """Internal diagnostics should be logged but not shown in the status bar."""
    window = _StatusWindow()
    issue = AnalysisNavigationPersistenceIssue(
        operation=AnalysisNavigationPersistenceOperation.LOAD,
        project_key=ProjectKey(value="saved:test", persistent=True),
        message="QSettings injected internal failure",
    )

    _show_analysis_navigation_persistence_error(issue, main_window=cast("MainWindow", window))

    assert window.messages == [
        (
            "Previous Analysis view settings could not be restored. Overview is shown; project data is unchanged.",
            5000,
        )
    ]
