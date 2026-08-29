"""Performance benchmarks for plotting data storage components."""

from __future__ import annotations

import time

import numpy as np
import pytest

from chappy.plotting.core.spectrum_data_store import SpectrumPlotDataStore


class TestPlotDataPerformance:
    """Performance tests for plot data storage."""

    @pytest.fixture
    def large_dataset(self) -> dict[str, np.ndarray]:
        """Create a large dataset for performance testing."""
        n_points = 50000
        return {
            "wavelength": np.linspace(1200, 1300, n_points),
            "flux": np.random.random(n_points),
            "error": np.random.random(n_points) * 0.1,
        }

    @pytest.mark.benchmark(group="plot_data_storage")
    def test_observed_data_storage_performance(
        self, benchmark, large_dataset: dict[str, np.ndarray]
    ) -> None:
        """Benchmark observed data storage throughput."""
        store = SpectrumPlotDataStore()

        def store_observed() -> dict[str, np.ndarray | None]:
            return store.set_observed_data(
                large_dataset["wavelength"], large_dataset["flux"], large_dataset["error"]
            )

        result = benchmark(store_observed)
        assert result["wavelength"] is not None
        assert len(result["wavelength"]) == len(large_dataset["wavelength"])
        assert benchmark.stats["mean"] < 0.1

    def test_memory_efficiency(self, large_dataset: dict[str, np.ndarray]) -> None:
        """Repeated storage should stay within a modest memory envelope."""
        import tracemalloc

        store = SpectrumPlotDataStore()
        tracemalloc.start()

        for _ in range(10):
            result = store.set_observed_data(
                large_dataset["wavelength"], large_dataset["flux"], large_dataset["error"]
            )
            assert result["wavelength"] is not None

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        mb_used = peak / 1024 / 1024
        assert mb_used < 100

    def test_performance_regression(self, large_dataset: dict[str, np.ndarray]) -> None:
        """Observed storage should remain within a practical latency budget."""
        store = SpectrumPlotDataStore()
        max_elapsed_seconds = 0.010

        start = time.perf_counter()
        result = store.set_observed_data(
            large_dataset["wavelength"], large_dataset["flux"], large_dataset["error"]
        )
        elapsed = time.perf_counter() - start

        assert result["wavelength"] is not None
        assert elapsed <= max_elapsed_seconds, (
            f"Performance regression: {elapsed:.6f}s exceeded {max_elapsed_seconds:.6f}s"
        )

    @pytest.mark.parametrize("n_points", [1000, 10000, 50000, 100000])
    def test_scaling_performance(self, n_points: int) -> None:
        """Observed storage should scale linearly with input size."""
        store = SpectrumPlotDataStore()
        wavelength = np.linspace(1200, 1300, n_points)
        flux = np.random.random(n_points)
        error = np.random.random(n_points) * 0.1

        start = time.perf_counter()
        result = store.set_observed_data(wavelength, flux, error)
        elapsed = time.perf_counter() - start

        assert result["wavelength"] is not None
        expected_time = n_points / 10000 * 0.001
        assert elapsed < expected_time * 2, (
            f"Poor scaling: {n_points} points took {elapsed:.3f}s (expected < {expected_time * 2:.3f}s)"
        )
