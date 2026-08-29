"""Structured logging helpers for interaction transitions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chappy.presentation.interaction.interaction_contracts import (
        InteractionChannel,
        InteractionPhase,
    )

_BASE_LOGGER: Final[logging.Logger] = logging.getLogger(__name__).getChild("interaction")


@dataclass(frozen=True)
class InteractionLogEntry:
    """Structured log entry for interaction transitions."""

    channel: InteractionChannel
    phase: InteractionPhase
    payload: Mapping[str, object] | None = None

    def to_json(self) -> str:
        """Return a JSON string representation suitable for structured logging."""
        model: dict[str, object] = {"channel": self.channel.value, "phase": self.phase.value}
        if self.payload:
            model["payload"] = dict(self.payload)
        return json.dumps(model, ensure_ascii=False, default=str)


class InteractionLogEmitter:
    """Emit structured logs for interaction transitions."""

    def __init__(
        self, channel: InteractionChannel, *, logger: logging.Logger | None = None
    ) -> None:
        """Initialise the emitter.

        Args:
            channel: Interaction channel for which the emitter is responsible.
            logger: Optional logger instance; defaults to the module-level interaction logger.
        """
        self._channel = channel
        self._logger = (
            logger.getChild(channel.value) if logger else _BASE_LOGGER.getChild(channel.value)
        )

    def emit(self, phase: InteractionPhase, payload: Mapping[str, object] | None = None) -> None:
        """Emit a structured log entry for the channel.

        Args:
            phase: Interaction phase associated with the log entry.
            payload: Additional contextual data.
        """
        entry = InteractionLogEntry(channel=self._channel, phase=phase, payload=payload)
        self._logger.debug(entry.to_json())
