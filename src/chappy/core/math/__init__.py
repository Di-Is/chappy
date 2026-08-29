"""Mathematical functions for spectral analysis."""

from .absorption_line import calculate_absorption_profile
from .voigt import voigt_profile

__all__ = ["calculate_absorption_profile", "voigt_profile"]
