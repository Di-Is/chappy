"""Best-effort execution for work that follows a scientific commit."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


def run_postcommit_actions_isolated(*actions: Callable[[], object]) -> None:
    """Run every post-commit action without misreporting science as rolled back."""
    for action in actions:
        try:
            action()
        except Exception:
            logger.exception("Post-commit action failed after scientific state was accepted")


__all__ = ["run_postcommit_actions_isolated"]
