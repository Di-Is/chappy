"""Helpers for applying interaction snapshot state."""

from __future__ import annotations

from chappy.presentation.interaction.interaction_contracts import (
    InteractionId,
    InteractionOutcome,
    InteractionPhase,
    InteractionStateSnapshot,
)

ACTIVE_PHASES = frozenset({InteractionPhase.ARMED, InteractionPhase.ACTIVE})


def build_snapshot_from_outcome[ContextT](
    outcome: InteractionOutcome[ContextT],
) -> InteractionStateSnapshot[ContextT]:
    """Build a state snapshot from a controller outcome."""
    return InteractionStateSnapshot(
        interaction_id=outcome.interaction_id,
        channel=outcome.channel,
        phase=outcome.phase,
        context=outcome.context,
    )


def active_interaction_id_for(
    *, phase: InteractionPhase, interaction_id: InteractionId
) -> InteractionId | None:
    """Return the active interaction id for a phase."""
    if phase in ACTIVE_PHASES:
        return interaction_id
    return None
