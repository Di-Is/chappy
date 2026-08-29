"""Optimizer convergence settings, optionally overridden per absorption region."""

from __future__ import annotations

from dataclasses import dataclass

SETTINGS_REGION_OPTIMIZER_KEY = "settings/optimizer/by_region"

DEFAULT_MAX_FUNCTION_EVALUATIONS = 1000
DEFAULT_TOLERANCE = 1e-8
DEFAULT_AUTO_CONTINUE = True

FIT_IMPROVEMENT_MIN = 1e-3
FIT_BOUNDARY_FRACTION = 1e-6

# Warm-restart bounds: a stalled fit is restarted from its best point up to this
# many rounds, stopping early once per-round chi-squared improvement falls below
# the plateau threshold.
MAX_OPTIMIZATION_ROUNDS = 5
FIT_PLATEAU_IMPROVEMENT = 1e-4


@dataclass(slots=True)
class OptimizerSettingsState:
    """Convergence hyperparameters applied to fits of one absorption region."""

    max_function_evaluations: int
    tolerance: float
    auto_continue: bool = DEFAULT_AUTO_CONTINUE


__all__ = [
    "DEFAULT_AUTO_CONTINUE",
    "DEFAULT_MAX_FUNCTION_EVALUATIONS",
    "DEFAULT_TOLERANCE",
    "FIT_BOUNDARY_FRACTION",
    "FIT_IMPROVEMENT_MIN",
    "FIT_PLATEAU_IMPROVEMENT",
    "MAX_OPTIMIZATION_ROUNDS",
    "SETTINGS_REGION_OPTIMIZER_KEY",
    "OptimizerSettingsState",
]
