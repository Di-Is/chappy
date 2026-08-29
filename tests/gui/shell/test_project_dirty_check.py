"""Tests for the GUI-shell dirty-file check (project_is_dirty).

These pin the dirty-tracking semantics that used to live on
``SpectroscopyProject.is_modified``/``project_filename`` before they moved to the GUI
shell boundary (see docs/task/core-project-refactor/plan.md, Phase 1,
P1-SESSION-BOUNDARY).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from chappy.core.components.absorber import AbsorberComponent
from chappy.core.spectroscopy_project import SpectroscopyProject
from chappy.gui.shell.project_file_coordinator import project_is_dirty


def test_project_is_dirty_without_recorded_path() -> None:
    """A project with no recorded session path counts as dirty."""
    project = SpectroscopyProject()

    assert project_is_dirty(project, None) is True


def test_project_is_dirty_when_recorded_file_is_missing(tmp_path: Path) -> None:
    """A recorded path pointing at a missing file counts as dirty."""
    project = SpectroscopyProject()
    missing = tmp_path / "missing.h5"

    assert project_is_dirty(project, str(missing)) is True


def test_project_is_dirty_false_when_saved_after_modification(tmp_path: Path) -> None:
    """A project saved after its last modification is not dirty."""
    project = SpectroscopyProject()
    target = tmp_path / "saved.h5"
    target.write_text("data", encoding="utf-8")
    now = datetime.now(UTC)
    os.utime(target, (now.timestamp(), now.timestamp()))
    project.modified = now - timedelta(seconds=5)

    assert project_is_dirty(project, str(target)) is False


def test_project_is_dirty_true_after_mutation_past_file_mtime(tmp_path: Path) -> None:
    """A mutation after save moves ``modified`` past the file mtime."""
    project = SpectroscopyProject()
    target = tmp_path / "saved.h5"
    target.write_text("data", encoding="utf-8")
    earlier = datetime.now(UTC) - timedelta(seconds=5)
    os.utime(target, (earlier.timestamp(), earlier.timestamp()))

    component = AbsorberComponent(
        name="Test Absorber", wavelength=1215.67, oscillator_strength=0.4164, gamma=6.265e8
    )
    project.model.add_component(component)

    assert project_is_dirty(project, str(target)) is True
