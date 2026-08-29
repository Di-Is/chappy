"""Continuum component for modeling spectrum continuum.

This implementation follows the Java version closely, using simple spline-based
continuum modeling with anchor points (DoublePairs in Java).
"""

import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import CubicSpline

from .base import ModelComponent

logger = logging.getLogger(__name__)

# Constants for continuum component
MIN_POINTS_FOR_CUBIC_SPLINE = 4
MIN_POINTS_FOR_LINEAR = 2
DEFAULT_CONTINUUM_FLUX = 1.0
MIN_WAVELENGTH_COVERAGE = 100.0  # Minimum 100 Å coverage


class ContinuumComponent(ModelComponent):
    """Component for modeling spectrum continuum using spline interpolation.

    This implementation follows the Java ContinuumComponent design:
    - Simple anchor points (wavelength, flux) list
    - Cubic B-spline interpolation
    - Interactive point addition/removal/movement
    - guessContin method with binning and percentile estimation
    """

    def __init__(self, name: str = "Continuum") -> None:
        """Initialize continuum component.

        Args:
            name: Component name
        """
        super().__init__(name)

        # Java equivalent: Vector continCPoints
        self.continuum_points: list[tuple[float, float]] = []

        # Sharing with Absorption mode - default to True for better user experience
        self.is_shared_with_absorption = True

    def num_continuum_points(self) -> int:
        """Get number of continuum points.

        Java equivalent: numContinPoints()

        Returns:
            Number of continuum points
        """
        return len(self.continuum_points)

    def add_continuum_point(self, wavelength: float, flux: float) -> None:
        """Add continuum point and sort by wavelength.

        Java equivalent: addContinPoint(DoublePair pair)

        Args:
            wavelength: Wavelength value
            flux: Flux value
        """
        self.continuum_points.append((wavelength, flux))
        self._sort_points()
        logger.debug("Added continuum point: %.1f Å, %.4f", wavelength, flux)

    def move_continuum_point(self, index: int, new_wavelength: float, new_flux: float) -> int:
        """Move continuum point to new position and re-sort.

        Java equivalent: moveContinPoint(int index, double newX, double newY)

        Args:
            index: Index of point to move
            new_wavelength: New wavelength
            new_flux: New flux

        Returns:
            New index after sorting
        """
        if 0 <= index < len(self.continuum_points):
            self.continuum_points[index] = (new_wavelength, new_flux)
            self._sort_points()
            # Find new index after sorting
            return self.closest_continuum_index(new_wavelength, new_flux)
        return index

    def remove_continuum_point_by_index(self, index: int) -> None:
        """Remove continuum point by index.

        Args:
            index: Index of point to remove
        """
        if 0 <= index < len(self.continuum_points):
            wavelength, flux = self.continuum_points[index]
            del self.continuum_points[index]
            logger.debug(
                "Removed continuum point at index %d: %.1f Å, %.4f", index, wavelength, flux
            )

    def closest_continuum_index(self, wavelength: float, flux: float) -> int:
        """Find index of closest continuum point.

        Java equivalent: continClosestIndex(DoublePair point)

        Args:
            wavelength: Target wavelength
            flux: Target flux

        Returns:
            Index of closest point
        """
        if not self.continuum_points:
            return 0

        min_dist_squared = float("inf")
        best_index = 0

        for i, (point_wave, point_flux) in enumerate(self.continuum_points):
            # 2D distance (wavelength + flux)
            dist_squared = (point_wave - wavelength) ** 2 + (point_flux - flux) ** 2
            if dist_squared < min_dist_squared:
                min_dist_squared = dist_squared
                best_index = i

        return best_index

    def _sort_points(self) -> None:
        """Sort continuum points by wavelength.

        Java equivalent: sort() method
        """
        self.continuum_points.sort(key=lambda point: point[0])  # Sort by wavelength

    def guess_continuum(
        self,
        wavelength: NDArray[np.floating[Any]],
        flux: NDArray[np.floating[Any]],
        bin_size: float = 100.0,
        cut_level: float = 0.95,
    ) -> None:
        """Automatically estimate continuum using binning and percentile estimation.

        This is a faithful implementation of the Java guessContin method.

        Java equivalent: guessContin(double binSize, double cutLevel)

        Args:
            wavelength: Wavelength array
            flux: Flux array
            bin_size: Width of wavelength bins in Angstroms
            cut_level: Percentile level for continuum estimation (0.95 = 95%)
        """
        if len(wavelength) == 0 or len(flux) == 0:
            logger.warning("Cannot guess continuum: empty data arrays")
            return
        if len(wavelength) != len(flux):
            msg = "Wavelength and flux arrays must have the same length"
            raise ValueError(msg)
        if not np.isfinite(bin_size) or bin_size <= 0:
            msg = "Continuum guess bin size must be finite and positive"
            raise ValueError(msg)
        if not np.isfinite(cut_level) or cut_level <= 0 or cut_level > 1:
            msg = "Continuum guess cut level must be in the range (0, 1]"
            raise ValueError(msg)

        # Clear existing points (Java: this.continCPoints = new Vector())
        self.continuum_points.clear()

        # Get wavelength range
        min_wave = float(np.min(wavelength))
        max_wave = float(np.max(wavelength))
        if not np.isfinite(min_wave) or not np.isfinite(max_wave):
            msg = "Continuum guess wavelength bounds must be finite"
            raise ValueError(msg)

        # Process bins from start to end
        swave = min_wave
        ewave = swave + bin_size

        while swave < max_wave:
            # Collect flux points in this wavelength bin
            flux_points: list[float] = []

            # Find indices within wavelength range [swave, ewave]
            mask = (wavelength >= swave) & (wavelength <= ewave)
            bin_flux = flux[mask]

            flux_points.extend(bin_flux)

            if flux_points:
                # Sort flux values (Java: Collections.sort(fluxPoints))
                flux_points.sort()

                # Get value at cut_level percentile (Java: int cindex = ((int) (fluxPoints.size() * cutLevel)) - 1)
                cindex = int(len(flux_points) * cut_level) - 1
                cindex = max(cindex, 0)

                continuum_value = flux_points[cindex]

                # Add continuum point at bin center
                bin_center = (swave + ewave) / 2.0
                self.add_continuum_point(bin_center, continuum_value)

            # Move to next bin
            swave += bin_size
            ewave += bin_size

        # Add boundary points (important for spline interpolation)
        # Java adds 3 duplicate points at each end for cubic spline boundary conditions
        if self.continuum_points:
            # First point: extend to minimum wavelength
            first_flux = self.continuum_points[0][1]
            for _ in range(3):
                self.add_continuum_point(min_wave, first_flux)

            # Last point: extend to maximum wavelength
            last_flux = self.continuum_points[-1][1]
            for _ in range(3):
                self.add_continuum_point(max_wave, last_flux)

        logger.info(
            "Guessed continuum with %d points (bin_size=%.1f, cut_level=%.2f)",
            len(self.continuum_points),
            bin_size,
            cut_level,
        )

    @staticmethod
    def calculate_from_points(
        points: list[tuple[float, float]], wavelength: NDArray[np.float64]
    ) -> NDArray[np.float64]:
        """Calculate continuum from arbitrary points without modifying instance state.

        This static method allows calculating continuum flux from any point list,
        useful for preview calculations during drag operations.

        Args:
            points: List of (wavelength, flux) anchor points
            wavelength: Wavelength array for interpolation

        Returns:
            Interpolated continuum flux values
        """
        if not points:
            return np.full_like(wavelength, DEFAULT_CONTINUUM_FLUX)

        waves = np.array([p[0] for p in points], dtype=np.float64)
        fluxes = np.array([p[1] for p in points], dtype=np.float64)

        # Collapse duplicate wavelengths so spline input is strictly increasing
        unique_waves, inverse_indices, counts = np.unique(
            waves, return_inverse=True, return_counts=True
        )
        if len(unique_waves) < len(waves):
            flux_sums = np.zeros_like(unique_waves, dtype=np.float64)
            np.add.at(flux_sums, inverse_indices, fluxes)
            fluxes = flux_sums / counts
            waves = unique_waves

        if len(waves) < MIN_POINTS_FOR_CUBIC_SPLINE:
            if len(waves) == 1:
                return np.full_like(wavelength, fluxes[0])
            result = np.interp(wavelength, waves, fluxes)
            return np.asarray(result, dtype=np.float64)

        try:
            spline = CubicSpline(waves, fluxes, bc_type="natural")
            result = spline(wavelength)
            return np.asarray(result, dtype=np.float64)

        except (ValueError, TypeError, IndexError):
            result = np.interp(wavelength, waves, fluxes)
            return np.asarray(result, dtype=np.float64)

    def calculate(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64]:
        """Calculate continuum using cubic B-spline interpolation.

        Java equivalent: calcSplineContin() + setContinLine()

        Args:
            wavelength: Wavelength array

        Returns:
            Continuum flux values
        """
        return ContinuumComponent.calculate_from_points(self.continuum_points, wavelength)

    def get_continuum_points(self) -> list[tuple[float, float]]:
        """Get anchor points (alias for continuum_points).

        Returns:
            List of (wavelength, flux) tuples
        """
        return self.continuum_points.copy()

    def set_continuum_points(self, points: list[tuple[float, float]]) -> None:
        """Set anchor points (alias for continuum_points).

        Args:
            points: List of (wavelength, flux) tuples
        """
        self.continuum_points = points.copy()
        self._sort_points()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContinuumComponent":
        """Create component from dictionary data.

        Args:
            data: Component data dictionary

        Returns:
            ContinuumComponent instance
        """
        component = cls(data.get("name", "Continuum"))

        # Set anchor points
        anchor_points = data.get("anchor_points", [])
        if anchor_points:
            component.set_continuum_points(anchor_points)

        # Set enabled state
        component.enabled = data.get("enabled", True)

        return component

    def export_for_absorption(self, wavelength: NDArray[np.float64]) -> NDArray[np.float64] | None:
        """Export continuum data for use in Absorption mode.

        Args:
            wavelength: Wavelength array for interpolation

        Returns:
            Normalized continuum flux array or None if not shareable
        """
        if not self.is_shared_with_absorption:
            return None

        # Validate before exporting
        is_valid, reason = self.validate_for_sharing()
        if not is_valid:
            logger.warning(
                "Cannot export continuum '%s' for absorption mode: %s", self.name, reason
            )
            return None

        continuum_flux = self.calculate(wavelength)
        logger.info("Exported continuum '%s' for absorption mode", self.name)
        return continuum_flux

    def validate_for_sharing(self) -> tuple[bool, str]:
        """Validate if continuum is suitable for sharing with absorption mode.

        Returns:
            Tuple of (is_valid, reason) where reason explains validation result
        """
        if len(self.continuum_points) < MIN_POINTS_FOR_LINEAR:
            return False, "Need at least 2 anchor points"

        if len(self.continuum_points) < MIN_POINTS_FOR_CUBIC_SPLINE:
            return False, "Need at least 4 anchor points for robust spline interpolation"

        # Check wavelength range coverage
        waves = [p[0] for p in self.continuum_points]
        wave_span = max(waves) - min(waves)
        if wave_span < MIN_WAVELENGTH_COVERAGE:
            return False, f"Wavelength coverage too narrow: {wave_span:.1f} Å"

        # Check for reasonable flux values
        fluxes = [p[1] for p in self.continuum_points]
        if any(f <= 0 for f in fluxes):
            return False, "Continuum contains non-positive flux values"

        return True, "Continuum is suitable for absorption mode"
