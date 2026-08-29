"""Localized primary messages for non-applied fit outcomes."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication

from chappy.core.components.optimize import FitOutcome


def localized_primary_message(outcome: str | None) -> str | None:
    """Return the localized primary line for a non-applied outcome, else None.

    Applied outcomes surface through the chi-squared status path and need no
    custom message here.
    """
    if outcome == FitOutcome.DEGENERATE.value:
        return QCoreApplication.translate(
            "FitOutcome",
            "This component is not supported by the data. "
            "Remove a component or widen the analysis range.",
        )
    if outcome == FitOutcome.BUDGET_STOPPED_STUCK.value:
        return QCoreApplication.translate(
            "FitOutcome",
            "The fit made little progress. Widen the analysis range or revise the initial values.",
        )
    if outcome == FitOutcome.NUMERICAL.value:
        return QCoreApplication.translate(
            "FitOutcome", "The fit hit a numerical problem. Fix any extreme initial values."
        )
    if outcome == FitOutcome.NO_FREE_PARAMS.value:
        return QCoreApplication.translate(
            "FitOutcome", "No parameters to optimize. Unfix at least one of z, logN, or b."
        )
    return None
