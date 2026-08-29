"""Settings adapter for optimize workflows."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings

from chappy.core.cosmology import PLANCK_2018, CosmologyParameters
from chappy.gui.modes.analysis.region_detail.tree.tree_header_controller import SavedTreeHeader

COSMOLOGY_H0_KEY = "settings/cosmology/H0"
COSMOLOGY_OMEGA_M_KEY = "settings/cosmology/Om"
COSMOLOGY_OMEGA_LAMBDA_KEY = "settings/cosmology/Ol"

TREE_HEADER_STATE_KEY = "optimize/tree/header_state"
TREE_HEADER_SCHEMA_KEY = "optimize/tree/header_schema"
TREE_SPECIES_WIDTH_PINNED_KEY = "optimize/tree/species_width_pinned"

ADVANCED_SETTINGS_EXPANDED_KEY = "analysis_detail/advanced_settings_expanded"


class OptimizeSettingsAdapter:
    """Load optimize workflow settings from Qt settings storage."""

    def __init__(self, settings: QSettings | None = None) -> None:
        """Initialize the adapter.

        Args:
            settings: Optional settings instance for tests or isolated storage.
        """
        self._settings = settings

    def load_cosmology_parameters(self) -> CosmologyParameters:
        """Load persisted cosmology parameters.

        Returns:
            Cosmology parameters used by optimize export.
        """
        settings = self._settings or QSettings("Chappy", "Chappy")
        return CosmologyParameters(
            h0=self._read_float(settings, COSMOLOGY_H0_KEY, PLANCK_2018.h0),
            omega_m=self._read_float(settings, COSMOLOGY_OMEGA_M_KEY, PLANCK_2018.omega_m),
            omega_lambda=self._read_float(
                settings, COSMOLOGY_OMEGA_LAMBDA_KEY, PLANCK_2018.omega_lambda
            ),
        )

    def load_tree_header_state(self) -> SavedTreeHeader | None:
        """Load the persisted optimize tree header layout.

        Returns:
            The saved header layout, or None when nothing usable is stored.
        """
        settings = self._settings or QSettings("Chappy", "Chappy")
        raw_state = settings.value(TREE_HEADER_STATE_KEY, None, type=QByteArray)
        raw_schema = settings.value(TREE_HEADER_SCHEMA_KEY, None, type=str)
        if not isinstance(raw_state, QByteArray) or raw_state.isEmpty():
            return None
        if not isinstance(raw_schema, str) or not raw_schema:
            return None
        return SavedTreeHeader(
            state=raw_state,
            schema=raw_schema,
            species_width_pinned=bool(
                settings.value(TREE_SPECIES_WIDTH_PINNED_KEY, False, type=bool)
            ),
        )

    def save_tree_header_state(self, saved: SavedTreeHeader) -> None:
        """Persist the optimize tree header layout.

        Args:
            saved: Header layout to store.
        """
        settings = self._settings or QSettings("Chappy", "Chappy")
        settings.setValue(TREE_HEADER_STATE_KEY, saved.state)
        settings.setValue(TREE_HEADER_SCHEMA_KEY, saved.schema)
        settings.setValue(TREE_SPECIES_WIDTH_PINNED_KEY, saved.species_width_pinned)

    def load_advanced_settings_expanded(self) -> bool:
        """Load whether the advanced settings card is expanded.

        Returns:
            True if the card was left expanded, False otherwise.
        """
        settings = self._settings or QSettings("Chappy", "Chappy")
        return bool(settings.value(ADVANCED_SETTINGS_EXPANDED_KEY, defaultValue=False, type=bool))

    def save_advanced_settings_expanded(self, expanded: bool) -> None:
        """Persist whether the advanced settings card is expanded.

        Args:
            expanded: Current expanded state of the advanced settings card.
        """
        settings = self._settings or QSettings("Chappy", "Chappy")
        settings.setValue(ADVANCED_SETTINGS_EXPANDED_KEY, expanded)

    @staticmethod
    def _read_float(settings: QSettings, key: str, default: float) -> float:
        """Read a float setting with a typed fallback."""
        value = settings.value(key, default, type=float)
        return float(value) if isinstance(value, int | float) else float(default)
