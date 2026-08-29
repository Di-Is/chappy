"""Global application settings and configuration."""

import logging
from typing import ClassVar, Self

logger = logging.getLogger(__name__)


class AppSettings:
    """Global application settings singleton."""

    _instance: ClassVar["Self | None"] = None
    _initialized: bool
    verbose: bool

    def __new__(cls) -> Self:
        """Create or return singleton instance."""
        instance = cls._instance
        if instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            instance.verbose = False
            cls._instance = instance
        return instance

    def __init__(self) -> None:
        """Initialize settings if not already initialized."""
        if self._initialized:
            return
        self.verbose = False
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "AppSettings":
        """Get the singleton instance."""
        return cls()

    def set_verbose(self, verbose: bool) -> None:
        """Set verbose mode.

        Args:
            verbose: Whether to enable verbose output
        """
        self.verbose = verbose
        logger.info("Verbose mode %s", "enabled" if verbose else "disabled")

    def is_verbose(self) -> bool:
        """Check if verbose mode is enabled.

        Returns:
            True if verbose mode is enabled
        """
        return self.verbose


# Convenience function
def is_verbose() -> bool:
    """Check if verbose mode is enabled.

    Returns:
        True if verbose mode is enabled
    """
    return AppSettings.get_instance().is_verbose()
