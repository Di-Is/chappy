"""Pure functions for Region Detail action-state and summary display selection."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto

from chappy.core.analysis import AnalysisReadiness
from chappy.presentation.optimize.models import (
    FitChi2View,
    FitCustomView,
    FitFailedView,
    FitRunningView,
    FitStatusView,
)


class FitBlockedReason(Enum):
    """Typed reason the fit action is currently unavailable.

    Each member maps one-to-one to a prerequisite already enforced by the
    fit enablement logic; no reason exists without such a source.
    """

    FIT_RUNNING = auto()
    NO_SPECTRUM = auto()
    NO_REGION_SELECTED = auto()
    NO_MODEL_COMPONENTS = auto()


class RegionDetailActionState(Enum):
    """Exclusive state selecting the single primary action of the panel."""

    NO_CONTEXT = auto()
    EMPTY = auto()
    NEEDS_FIT = auto()
    FITTED = auto()


@dataclass(frozen=True, slots=True)
class RegionDetailActionInputs:
    """Facts the action-state classification is derived from."""

    fit_running: bool
    has_spectrum: bool
    has_region_selected: bool
    has_model_components: bool
    readiness: AnalysisReadiness


def fit_blocked_reason(inputs: RegionDetailActionInputs) -> FitBlockedReason | None:
    """Return the typed reason the fit action is unavailable, if any."""
    if inputs.fit_running:
        return FitBlockedReason.FIT_RUNNING
    if not inputs.has_spectrum:
        return FitBlockedReason.NO_SPECTRUM
    if not inputs.has_region_selected:
        return FitBlockedReason.NO_REGION_SELECTED
    if not inputs.has_model_components:
        return FitBlockedReason.NO_MODEL_COMPONENTS
    return None


def action_state(inputs: RegionDetailActionInputs) -> RegionDetailActionState:
    """Derive the exclusive action state from existing fit prerequisites."""
    reason = fit_blocked_reason(inputs)
    if reason in (FitBlockedReason.NO_SPECTRUM, FitBlockedReason.NO_REGION_SELECTED):
        return RegionDetailActionState.NO_CONTEXT
    if reason is FitBlockedReason.NO_MODEL_COMPONENTS:
        return RegionDetailActionState.EMPTY
    if inputs.readiness is AnalysisReadiness.LATEST:
        return RegionDetailActionState.FITTED
    return RegionDetailActionState.NEEDS_FIT


@dataclass(frozen=True, slots=True)
class SummaryStatePlaceholder:
    """No summary state is available yet."""


@dataclass(frozen=True, slots=True)
class SummaryStateOptimizing:
    """A fit is currently running."""


@dataclass(frozen=True, slots=True)
class SummaryStateFailed:
    """The most recent fit failed."""


@dataclass(frozen=True, slots=True)
class SummaryStateFitted:
    """The region has an up-to-date fit."""


@dataclass(frozen=True, slots=True)
class SummaryStateNeedsOptimization:
    """The region structure changed since the last fit."""


@dataclass(frozen=True, slots=True)
class SummaryStateNotFitted:
    """The region has never been fitted."""


type SummaryStateDisplay = (
    SummaryStatePlaceholder
    | SummaryStateOptimizing
    | SummaryStateFailed
    | SummaryStateFitted
    | SummaryStateNeedsOptimization
    | SummaryStateNotFitted
)


def summary_state_display(
    state: RegionDetailActionState, readiness: AnalysisReadiness, status: FitStatusView
) -> SummaryStateDisplay:
    """Select the results-card state display from action state and fit status."""
    if isinstance(status, FitRunningView):
        return SummaryStateOptimizing()
    if isinstance(status, FitFailedView):
        return SummaryStateFailed()
    if state is RegionDetailActionState.NO_CONTEXT:
        return SummaryStatePlaceholder()
    if state is RegionDetailActionState.FITTED:
        return SummaryStateFitted()
    if readiness is AnalysisReadiness.STALE:
        return SummaryStateNeedsOptimization()
    return SummaryStateNotFitted()


@dataclass(frozen=True, slots=True)
class SummaryFitPlaceholder:
    """No chi-squared statistic is available."""


@dataclass(frozen=True, slots=True)
class SummaryFitChi2:
    """A chi-squared statistic is available, optionally with a reduced value."""

    chi2: float
    reduced: float | None


type SummaryFitDisplay = SummaryFitPlaceholder | SummaryFitChi2


def summary_fit_display(
    status: FitStatusView, *, project_chi2: float | None, project_reduced: float | None
) -> SummaryFitDisplay:
    """Select the fit-statistic display, preferring the stored project summary."""
    chi2 = project_chi2
    reduced = project_reduced
    if chi2 is None and isinstance(status, FitChi2View):
        chi2 = status.chi2
        reduced = status.reduced
    if chi2 is None or not math.isfinite(chi2):
        return SummaryFitPlaceholder()
    if reduced is not None and not math.isfinite(reduced):
        reduced = None
    return SummaryFitChi2(chi2=chi2, reduced=reduced)


@dataclass(frozen=True, slots=True)
class SummaryNoteHidden:
    """No note should be shown."""


@dataclass(frozen=True, slots=True)
class SummaryNoteCustomMessage:
    """Show an application-supplied status message verbatim."""

    message: str


@dataclass(frozen=True, slots=True)
class SummaryNoteBlocked:
    """Show why the fit action is currently blocked."""

    reason: FitBlockedReason


@dataclass(frozen=True, slots=True)
class SummaryNoteAddModelComponent:
    """Prompt the user to add a model component before fitting."""


@dataclass(frozen=True, slots=True)
class SummaryNoteStaleRegion:
    """Prompt the user to re-run the fit after a structure change."""


@dataclass(frozen=True, slots=True)
class SummaryNoteRunFit:
    """Prompt the user to run the first fit."""


type SummaryNoteDisplay = (
    SummaryNoteHidden
    | SummaryNoteCustomMessage
    | SummaryNoteBlocked
    | SummaryNoteAddModelComponent
    | SummaryNoteStaleRegion
    | SummaryNoteRunFit
)


def summary_note_display(
    state: RegionDetailActionState,
    readiness: AnalysisReadiness,
    status: FitStatusView,
    blocked_reason: FitBlockedReason | None,
) -> SummaryNoteDisplay:
    """Select the results-card note display."""
    if isinstance(status, FitCustomView) and status.message:
        return SummaryNoteCustomMessage(message=status.message)
    if isinstance(status, FitRunningView):
        return SummaryNoteHidden()
    if state is RegionDetailActionState.NO_CONTEXT:
        if blocked_reason is not None:
            return SummaryNoteBlocked(reason=blocked_reason)
        return SummaryNoteHidden()
    if state is RegionDetailActionState.EMPTY:
        return SummaryNoteAddModelComponent()
    if state is RegionDetailActionState.NEEDS_FIT:
        if readiness is AnalysisReadiness.STALE:
            return SummaryNoteStaleRegion()
        return SummaryNoteRunFit()
    return SummaryNoteHidden()
