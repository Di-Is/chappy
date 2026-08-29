"""Interactive components for plotting functionality.

This module contains interactive components extracted from the monolithic plot
classes to improve maintainability and code reuse.
"""

from __future__ import annotations

from .continuum_editor import MatplotlibContinuumEditor
from .selection_handler import MatplotlibSelectionHandler, SelectionMode

__all__ = ["MatplotlibContinuumEditor", "MatplotlibSelectionHandler", "SelectionMode"]
