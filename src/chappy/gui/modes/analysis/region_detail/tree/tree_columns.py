"""Column definitions for optimize parameter trees."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt


@dataclass(frozen=True)
class ColumnMeta:
    """Metadata for one optimize tree column."""

    key: str
    source_text: str
    format_spec: str | None = None
    visible_by_default: bool = True


# Data roles carrying unformatted parameter values, used by the editing delegate
# and by any future sorting support without re-parsing the display text.
ROLE_RAW_VALUE = int(Qt.ItemDataRole.UserRole) + 1
ROLE_RAW_ERROR = int(Qt.ItemDataRole.UserRole) + 2
ROLE_EDIT_KIND = int(Qt.ItemDataRole.UserRole) + 3
ROLE_LINE_IDS = int(Qt.ItemDataRole.UserRole) + 4


class TreeCellEditKind(StrEnum):
    """Typed edit contract stored on each potentially editable tree cell."""

    COMPONENT_PARAMETER = "component_parameter"
    LINE_ANALYSIS_HALF_WIDTH = "line_analysis_half_width"
    NONE = "none"


# Column definitions (single source of truth for column order).
# To add/reorder columns, modify COLUMNS only - COL_* constants are derived automatically.
COLUMNS: tuple[ColumnMeta, ...] = (
    ColumnMeta("ID", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "ID"))),
    ColumnMeta("SPECIES", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "Species"))),
    ColumnMeta("Z", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "z")), format_spec="{:.5f}"),
    ColumnMeta("LOGN", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "logN")), format_spec="{:.2f}"),
    ColumnMeta("B", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "b")), format_spec="{:.1f}"),
    ColumnMeta("CF", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "Cf")), format_spec="{:.3f}"),
    ColumnMeta(
        "ANALYSIS_HALF_WIDTH", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "Analysis range [km/s]"))
    ),
    ColumnMeta(
        "WAVELENGTH", str(QT_TRANSLATE_NOOP("RegionDetailPanel", "λ [Å]")), format_spec="{:.2f}"
    ),
    ColumnMeta(
        "LOOKBACK",
        str(QT_TRANSLATE_NOOP("RegionDetailPanel", "Lookback time [Gyr]")),
        format_spec="{:.3f}",
    ),
    ColumnMeta(
        "COMOVING",
        str(QT_TRANSLATE_NOOP("RegionDetailPanel", "Comoving distance [Mpc]")),
        format_spec="{:.1f}",
    ),
)

# Column index lookup derived from COLUMNS.
COL_INDEX: dict[str, int] = {col.key: i for i, col in enumerate(COLUMNS)}

COL_ID = COL_INDEX["ID"]
COL_SPECIES = COL_INDEX["SPECIES"]
COL_Z = COL_INDEX["Z"]
COL_LOGN = COL_INDEX["LOGN"]
COL_B = COL_INDEX["B"]
COL_CF = COL_INDEX["CF"]
COL_ANALYSIS_HALF_WIDTH = COL_INDEX["ANALYSIS_HALF_WIDTH"]
COL_WAVELENGTH = COL_INDEX["WAVELENGTH"]
COL_LOOKBACK = COL_INDEX["LOOKBACK"]
COL_COMOVING = COL_INDEX["COMOVING"]

PARAMETER_CONFIGS: tuple[tuple[str, int, str, float], ...] = (
    ("redshift", COL_Z, "{:.5f}", 0.0),
    ("column_density", COL_LOGN, "{:.2f}", 0.0),
    ("b_parameter", COL_B, "{:.1f}", 0.0),
    ("covering_factor", COL_CF, "{:.3f}", 1.0),
)

PARAMETER_COLUMNS: dict[int, str] = {
    value_col: param for param, value_col, _fmt, _default in PARAMETER_CONFIGS
}


@dataclass(frozen=True)
class TreeColumnProfile:
    """Initial column visibility and visual order for one audience."""

    hidden_keys: frozenset[str]
    visual_order: tuple[str, ...] | None  # None = keep COLUMNS definition order


RESEARCHER_PROFILE = TreeColumnProfile(
    hidden_keys=frozenset({"LOOKBACK", "COMOVING"}), visual_order=None
)

CITIZEN_SCIENTIST_PROFILE = TreeColumnProfile(
    hidden_keys=frozenset(),
    visual_order=(
        "ID",
        "SPECIES",
        "Z",
        "LOOKBACK",
        "COMOVING",
        "LOGN",
        "B",
        "CF",
        "ANALYSIS_HALF_WIDTH",
        "WAVELENGTH",
    ),
)

# Column profile applied when no persisted header state exists.
# Swap this constant to change the shipped default for a distribution.
DEFAULT_PROFILE = CITIZEN_SCIENTIST_PROFILE
