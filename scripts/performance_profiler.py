"""Performance profiling utilities for measuring code execution time.

This module provides decorators and context managers for performance measurement
without polluting the main codebase. Profiling can be enabled via environment variable.
"""  # noqa: INP001

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)

# Environment variable to enable profiling
_PROFILE_ENABLED = os.getenv("CHAPPY_PROFILE_PERFORMANCE", "false").lower() == "true"
_PROFILE_OUTPUT_DIR = Path(os.getenv("CHAPPY_PROFILE_OUTPUT_DIR", "performance_logs"))


@dataclass
class ProfileRecord:
    """Single performance measurement record."""

    function_name: str
    elapsed_time_ms: float
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class PerformanceProfiler:
    """Thread-safe performance profiler for collecting timing data."""

    def __init__(self, output_dir: Path | None = None) -> None:
        """Initialize profiler.

        Args:
            output_dir: Directory to save profile results. Defaults to performance_logs/.
        """
        self._output_dir = output_dir or _PROFILE_OUTPUT_DIR
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._records: list[ProfileRecord] = []
        self._lock = Lock()
        self._enabled = _PROFILE_ENABLED

    def is_enabled(self) -> bool:
        """Check if profiling is enabled."""
        return self._enabled

    def record(
        self, function_name: str, elapsed_time_ms: float, *, metadata: dict[str, Any] | None = None
    ) -> None:
        """Record a performance measurement.

        Args:
            function_name: Name of the function or operation being measured.
            elapsed_time_ms: Elapsed time in milliseconds.
            metadata: Optional metadata to include with the measurement.
        """
        if not self._enabled:
            return

        record = ProfileRecord(
            function_name=function_name,
            elapsed_time_ms=elapsed_time_ms,
            timestamp=time.time(),
            metadata=metadata or {},
        )

        with self._lock:
            self._records.append(record)

    @contextmanager
    def measure(
        self, operation_name: str, *, metadata: dict[str, Any] | None = None
    ) -> Iterator[None]:
        """Context manager for measuring operation time.

        Args:
            operation_name: Name of the operation being measured.
            metadata: Optional metadata to include with the measurement.

        Yields:
            None
        """
        if not self._enabled:
            yield
            return

        start_time = time.perf_counter()
        try:
            yield
        finally:
            elapsed_time = (time.perf_counter() - start_time) * 1000.0  # Convert to ms
            self.record(operation_name, elapsed_time, metadata=metadata)

    def save_results(self, filename: str | None = None) -> Path:
        """Save collected records to a JSON file.

        Args:
            filename: Output filename. If None, uses timestamp-based name.

        Returns:
            Path to the saved file.
        """
        if not self._enabled:
            return self._output_dir / "profiling_disabled.txt"

        if filename is None:
            timestamp = int(time.time())
            filename = f"profile_{timestamp}.json"

        output_path = self._output_dir / filename

        with self._lock:
            records_data = [record.to_dict() for record in self._records]

        with output_path.open("w", encoding="utf-8") as f:
            json.dump({"total_records": len(records_data), "records": records_data}, f, indent=2)

        logger.info("Performance profile saved to %s (%d records)", output_path, len(records_data))
        return output_path

    def clear(self) -> None:
        """Clear all collected records."""
        with self._lock:
            self._records.clear()

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics of collected records.

        Returns:
            Dictionary with summary statistics.
        """
        if not self._enabled or not self._records:
            return {"enabled": False, "total_records": 0}

        with self._lock:
            records = self._records.copy()

        if not records:
            return {"enabled": True, "total_records": 0}

        # Group by function name
        by_function: dict[str, list[float]] = {}
        for record in records:
            by_function.setdefault(record.function_name, []).append(record.elapsed_time_ms)

        summary: dict[str, Any] = {"enabled": True, "total_records": len(records), "functions": {}}

        for func_name, times in by_function.items():
            summary["functions"][func_name] = {
                "count": len(times),
                "total_ms": sum(times),
                "mean_ms": sum(times) / len(times),
                "min_ms": min(times),
                "max_ms": max(times),
            }

        return summary


# Global profiler instance
_global_profiler = PerformanceProfiler()


def profile_function(
    name: str | None = None, *, metadata: dict[str, Any] | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to profile function execution time.

    Args:
        name: Custom name for the operation. If None, uses function name.
        metadata: Optional metadata to include with measurements.

    Returns:
        Decorator function.

    Example:
        @profile_function()
        def my_function():
            pass

        @profile_function(name="custom_name", metadata={"key": "value"})
        def another_function():
            pass
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        operation_name = name or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with _global_profiler.measure(operation_name, metadata=metadata):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance.

    Returns:
        Global PerformanceProfiler instance.
    """
    return _global_profiler
