#!/usr/bin/env python3
"""Script to measure baseline performance of line selection dialog.

This script uses monkey patching to measure performance without modifying
the main codebase. It wraps key methods externally for E2E measurement.

Usage:
    CHAPPY_PROFILE_PERFORMANCE=true uv run python scripts/measure_line_selection_performance.py
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from types import TracebackType


class MeasurementContextProtocol(Protocol):
    """Context manager protocol for profiling scopes."""

    def __enter__(self) -> None:
        """Enter measurement context."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Exit measurement context."""


class PerformanceProfilerProtocol(Protocol):
    """Protocol describing the profiler capabilities consumed by this script."""

    def is_enabled(self) -> bool:
        """Return whether profiling is enabled."""

    def measure(
        self, operation_name: str, *, metadata: dict[str, object] | None = None
    ) -> MeasurementContextProtocol:
        """Return a context manager that records the wrapped operation."""

    def get_summary(self) -> dict[str, object]:
        """Return a dictionary summary of collected measurements."""

    def save_results(self, filename: str) -> Path:
        """Persist profiling results to disk."""


class ProfilerFactoryProtocol(Protocol):
    """Callable returning a configured profiler instance."""

    def __call__(self) -> PerformanceProfilerProtocol:
        """Create or fetch a profiler instance."""


class TableItemProtocol(Protocol):
    """Subset of QTableWidgetItem used by this script."""

    def flags(self) -> int:
        """Return item flags."""

    def checkState(self) -> int:  # noqa: N802 - Qt API name
        """Return current check state."""

    def setCheckState(self, state: int) -> None:  # noqa: N802 - Qt API name
        """Update the check state."""


class TableWidgetProtocol(Protocol):
    """Subset of QTableWidget used by this script."""

    def rowCount(self) -> int:  # noqa: N802 - Qt API name
        """Return number of rows."""

    def item(self, row: int, column: int) -> TableItemProtocol | None:
        """Return the item at the requested position if available."""


class LineSelectionDialogProtocol(Protocol):
    """Subset of LineSelectionDialog interface used in the measurement."""

    _table: TableWidgetProtocol | None
    _filtered_lines: list[object]

    def __init__(self) -> None:
        """Construct the dialog."""

    def show(self) -> None:
        """Display the dialog."""

    def accept(self) -> None:
        """Close the dialog as if the user accepted it."""


class ApplicationProtocol(Protocol):
    """Subset of QApplication methods used by this script."""

    def __init__(self, argv: list[str]) -> None:
        """Construct the application with system arguments."""

    def processEvents(self) -> None:  # noqa: N802 - Qt API name
        """Process queued UI events."""


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
PERFORMANCE_ENV_VAR = "CHAPPY_PROFILE_PERFORMANCE"


def _prepare_environment() -> None:
    """Ensure sys.path and profiling env var are configured before imports."""
    src_as_str = str(SRC_PATH)
    if src_as_str not in sys.path:
        sys.path.insert(0, src_as_str)
    if os.getenv(PERFORMANCE_ENV_VAR, "false").lower() != "true":
        os.environ[PERFORMANCE_ENV_VAR] = "true"


def _load_runtime_dependencies() -> tuple[
    object, type[ApplicationProtocol], type[LineSelectionDialogProtocol], ProfilerFactoryProtocol
]:
    """Import Qt and Chappy modules only after environment preparation."""
    qt_core = importlib.import_module("PySide6.QtCore")
    qt_widgets = importlib.import_module("PySide6.QtWidgets")
    dialog_module = importlib.import_module("chappy.gui.dialogs.line_selection_dialog")
    profiler_module = importlib.import_module("performance_profiler")

    return (
        qt_core.Qt,
        qt_widgets.QApplication,
        dialog_module.LineSelectionDialog,
        profiler_module.get_profiler,
    )


def _wrap_dialog_method_for_profiling(
    dialog_cls: type[LineSelectionDialogProtocol],
    method_name: str,
    *,
    profiler: PerformanceProfilerProtocol,
) -> None:
    """Wrap a LineSelectionDialog method before instantiation.

    Args:
        dialog_cls: LineSelectionDialog concrete class.
        method_name: Target method name.
        profiler: Shared PerformanceProfiler instance.
    """
    if not profiler.is_enabled():
        return

    original_method = getattr(dialog_cls, method_name, None)
    if original_method is None:
        msg = f"LineSelectionDialog has no method named {method_name}"
        raise AttributeError(msg)
    if not callable(original_method):
        msg = f"Attribute {method_name} is not callable"
        raise TypeError(msg)
    if getattr(original_method, "_profiling_wrapped", False):
        return

    @wraps(original_method)
    def wrapped_method(
        self: LineSelectionDialogProtocol, *args: object, **kwargs: object
    ) -> object:
        metadata: dict[str, object] = {}
        table: TableWidgetProtocol | None = self._table
        if table is not None:
            metadata["row_count"] = table.rowCount()
        metadata["line_count"] = len(self._filtered_lines)

        with profiler.measure(f"{self.__class__.__name__}.{method_name}", metadata=metadata):
            return original_method(self, *args, **kwargs)

    wrapped_method._profiling_wrapped = True
    setattr(dialog_cls, method_name, wrapped_method)


def _install_profiling_wrappers(
    dialog_cls: type[LineSelectionDialogProtocol],
    methods: tuple[str, ...],
    *,
    profiler: PerformanceProfilerProtocol,
) -> None:
    """Install profiling wrappers for the requested methods.

    Args:
        dialog_cls: LineSelectionDialog concrete class.
        methods: Tuple of method names to wrap.
        profiler: Shared PerformanceProfiler instance.
    """
    if not profiler.is_enabled():
        return

    for method_name in methods:
        _wrap_dialog_method_for_profiling(dialog_cls, method_name, profiler=profiler)


def main() -> int:
    """Run performance measurement."""
    _prepare_environment()
    (qt_namespace, application_cls, dialog_cls, profiler_factory) = _load_runtime_dependencies()

    app = application_cls(sys.argv)

    profiler = profiler_factory()
    methods_to_profile = (
        "_on_item_changed",
        "_apply_multiplet_highlight",
        "_update_checkbox_sort_keys",
        "_row_for_line",
        "_populate_table",
    )
    _install_profiling_wrappers(dialog_cls, methods_to_profile, profiler=profiler)

    # Create dialog
    dialog = dialog_cls()

    # Show dialog
    dialog.show()

    # Wait for dialog to be ready
    app.processEvents()
    time.sleep(0.5)  # Wait for table to populate

    # Get table widget
    table = dialog._table
    if not table:
        return 1

    row_count = table.rowCount()

    # Simulate checkbox clicks on first 10 rows
    for row in range(min(10, row_count)):
        checkbox_item = table.item(row, 0)
        if checkbox_item and checkbox_item.flags() & qt_namespace.ItemFlag.ItemIsUserCheckable:
            # Toggle checkbox
            current_state = checkbox_item.checkState()
            new_state = (
                qt_namespace.CheckState.Unchecked
                if current_state == qt_namespace.CheckState.Checked
                else qt_namespace.CheckState.Checked
            )
            checkbox_item.setCheckState(new_state)
            app.processEvents()

    # Close dialog
    dialog.accept()

    # Get summary
    summary = profiler.get_summary()

    for _stats in summary.get("functions", {}).values():
        pass

    # Save results
    timestamp = int(time.time())
    filename = f"line_selection_dialog_{timestamp}.json"
    profiler.save_results(filename)

    return 0


if __name__ == "__main__":
    sys.exit(main())
