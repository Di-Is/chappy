"""Atomic line data model and in-memory query indexes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

LineIdentifier = str

logger = logging.getLogger(__name__)

_ELEMENT_SYMBOLS_BY_ATOMIC_NUMBER = (
    "H",
    "HE",
    "LI",
    "BE",
    "B",
    "C",
    "N",
    "O",
    "F",
    "NE",
    "NA",
    "MG",
    "AL",
    "SI",
    "P",
    "S",
    "CL",
    "AR",
    "K",
    "CA",
    "SC",
    "TI",
    "V",
    "CR",
    "MN",
    "FE",
    "CO",
    "NI",
    "CU",
    "ZN",
    "GA",
    "GE",
    "AS",
    "SE",
    "BR",
    "KR",
    "RB",
    "SR",
    "Y",
    "ZR",
    "NB",
    "MO",
    "TC",
    "RU",
    "RH",
    "PD",
    "AG",
    "CD",
    "IN",
    "SN",
    "SB",
    "TE",
    "I",
    "XE",
    "CS",
    "BA",
    "LA",
    "CE",
    "PR",
    "ND",
    "PM",
    "SM",
    "EU",
    "GD",
    "TB",
    "DY",
    "HO",
    "ER",
    "TM",
    "YB",
    "LU",
    "HF",
    "TA",
    "W",
    "RE",
    "OS",
    "IR",
    "PT",
    "AU",
    "HG",
    "TL",
    "PB",
    "BI",
    "PO",
    "AT",
    "RN",
    "FR",
    "RA",
    "AC",
    "TH",
    "PA",
    "U",
    "NP",
    "PU",
    "AM",
    "CM",
    "BK",
    "CF",
    "ES",
    "FM",
    "MD",
    "NO",
    "LR",
    "RF",
    "DB",
    "SG",
    "BH",
    "HS",
    "MT",
    "DS",
    "RG",
    "CN",
    "NH",
    "FL",
    "MC",
    "LV",
    "TS",
    "OG",
)
_ELEMENT_ORDER = {
    symbol: atomic_number
    for atomic_number, symbol in enumerate(_ELEMENT_SYMBOLS_BY_ATOMIC_NUMBER, start=1)
}


def normalize_element_symbol(symbol: str) -> str:
    """Return a consistently cased element symbol suitable for display."""
    normalized = symbol.strip()
    if not normalized:
        return ""

    head = normalized[0].upper()
    tail = "".join(
        character.lower() if character.isalpha() else character for character in normalized[1:]
    )
    return head + tail


IONIZATION_ROMAN = dict(
    enumerate(
        [
            "I",
            "II",
            "III",
            "IV",
            "V",
            "VI",
            "VII",
            "VIII",
            "IX",
            "X",
            "XI",
            "XII",
            "XIII",
            "XIV",
            "XV",
            "XVI",
            "XVII",
            "XVIII",
            "XIX",
            "XX",
            "XXI",
            "XXII",
            "XXIII",
            "XXIV",
            "XXV",
            "XXVI",
            "XXVII",
            "XXVIII",
            "XXIX",
            "XXX",
        ]
    )
)


def charge_to_stage(charge_state: int | None) -> str:
    """Convert charge state (0-indexed) to spectroscopic ionization stage."""
    if charge_state is None:
        return ""
    return IONIZATION_ROMAN.get(charge_state, f"{charge_state + 1}")


def stage_to_charge(stage: str | None) -> int | None:
    """Convert ionization stage (Roman numeral) back to charge state."""
    if not stage:
        return None
    normalized = stage.strip().upper()
    for charge, roman in IONIZATION_ROMAN.items():
        if roman == normalized:
            return charge
    try:
        numeric = int(normalized)
    except ValueError:
        return None
    return max(numeric - 1, 0)


@dataclass(frozen=True)
class SearchFilters:
    """Search filters for atomic line queries."""

    query: str = ""
    element_filter: str = ""
    charge_state: int | None = None
    wavelength_min: float | None = None
    wavelength_max: float | None = None
    multiplet_filter: str = ""
    only_multiplets: bool = False


@dataclass(frozen=True)
class AtomicLine:
    """Atomic transition line data for spectroscopy workflows."""

    line_identifier: str
    species: str
    wavelength_angstrom: float
    oscillator_strength: float
    gamma_value: float
    multiplet_id: str = ""
    comments: str = ""
    element_symbol: str = ""
    charge_state: int | None = None
    transition_name: str = ""
    wavelength_source: str = ""
    wavelength_ritz: float | None = None
    wavelength_ritz_uncertainty: float | None = None
    wavelength_observed: float | None = None
    wavelength_observed_uncertainty: float | None = None
    energy_lower_ev: float | None = None
    energy_upper_ev: float | None = None
    lower_configuration: str = ""
    lower_term: str = ""
    lower_j: str = ""
    upper_configuration: str = ""
    upper_term: str = ""
    upper_j: str = ""
    upper_term_ls: str = ""
    accuracy_code: str = ""
    multiplet_label: str = ""
    component_index: int | None = None
    transition_probability_ref: str = ""
    wavelength_ref: str = ""

    def __post_init__(self) -> None:
        """Validate atomic line data after initialization."""
        if self.wavelength_angstrom <= 0:
            msg = f"Wavelength must be positive: {self.wavelength_angstrom}"
            raise ValueError(msg)
        if self.oscillator_strength < 0:
            msg = f"Oscillator strength must be non-negative: {self.oscillator_strength}"
            raise ValueError(msg)
        if self.gamma_value < 0:
            msg = f"Gamma value must be non-negative: {self.gamma_value}"
            raise ValueError(msg)

    @property
    def element(self) -> str:
        """Extract element name from species."""
        return self.species.split()[0] if " " in self.species else self.species

    @property
    def is_valid(self) -> bool:
        """Check if this line has valid data for modeling."""
        return (
            self.wavelength_angstrom > 0 and self.oscillator_strength > 0 and self.gamma_value > 0
        )

    def __str__(self) -> str:
        """String representation for display."""
        return f"{self.species} {self.wavelength_angstrom:.2f} Å"

    @property
    def ionization_stage(self) -> str:
        """Return ionization stage (Roman numeral) if available."""
        return charge_to_stage(self.charge_state)

    @property
    def line_id(self) -> LineIdentifier:
        """Return the persistent identifier supplied by the database."""
        if not self.line_identifier:
            msg = "AtomicLine missing line_identifier"
            raise RuntimeError(msg)
        return self.line_identifier

    @property
    def energy_gap_ev(self) -> float | None:
        """Return excitation energy difference if both levels are defined."""
        if self.energy_lower_ev is None or self.energy_upper_ev is None:
            return None
        return self.energy_upper_ev - self.energy_lower_ev


class AtomicLineData:
    """In-memory atomic line query repository."""

    def __init__(self, lines: Iterable[AtomicLine] | None = None) -> None:
        """Initialize query indexes from atomic lines.

        Args:
            lines: Atomic lines to index. ``None`` creates an empty repository.
        """
        self.lines: list[AtomicLine] = [line for line in lines or () if line.is_valid]
        self._element_index: dict[str, list[AtomicLine]] = {}
        self._line_index: dict[LineIdentifier, AtomicLine] = {}
        self._wavelength_index: dict[tuple[str, float], AtomicLine] = {}
        self._build_indices()

    def _build_indices(self) -> None:
        """Build search indices for fast filtering."""
        self._element_index.clear()
        for line in self.lines:
            element = (line.element_symbol or line.element).upper()
            if not element:
                continue
            self._element_index.setdefault(element, []).append(line)

        self._line_index = {line.line_id: line for line in self.lines}
        self._build_wavelength_index()

    def _build_wavelength_index(self) -> None:
        """Build species + wavelength index for O(1) lookup.

        Index key: (species, round(wavelength, 3))
        On collision: keep the line with higher oscillator_strength (f-value)
        """
        self._wavelength_index.clear()
        for line in self.lines:
            key = (line.species, round(line.wavelength_angstrom, 3))
            existing = self._wavelength_index.get(key)
            if existing is not None:
                if line.oscillator_strength <= existing.oscillator_strength:
                    continue
                logger.debug(
                    "Wavelength index collision: %s, keeping %s (f=%.4f) over %s (f=%.4f)",
                    key,
                    line.line_id,
                    line.oscillator_strength,
                    existing.line_id,
                    existing.oscillator_strength,
                )
            self._wavelength_index[key] = line

    def get_lines_by_multiplet(self, multiplet_id: str) -> list[AtomicLine]:
        """Get all lines in a multiplet group."""
        if not multiplet_id:
            return []
        return [line for line in self.lines if line.multiplet_id == multiplet_id]

    def has_multiplet_siblings(self, line: AtomicLine) -> bool:
        """Check if line has multiplet siblings."""
        if not line.multiplet_id:
            return False
        siblings = self.get_lines_by_multiplet(line.multiplet_id)
        return len(siblings) > 1

    def get_line_by_id(self, line_id: LineIdentifier) -> AtomicLine | None:
        """Fast lookup of atomic line by persistent identifier."""
        return self._line_index.get(line_id)

    def get_line_by_species_wavelength(self, species: str, wavelength: float) -> AtomicLine | None:
        """Lookup atomic line by species and wavelength."""
        key = (species, round(wavelength, 3))
        return self._wavelength_index.get(key)

    def search_lines(self, filters: SearchFilters | None = None) -> list[AtomicLine]:
        """Search atomic lines with multiple filters."""
        if filters is None:
            filters = SearchFilters()

        results = self.lines.copy()

        if filters.query:
            query = filters.query.upper()
            results = [
                line
                for line in results
                if (
                    query in line.species.upper()
                    or query in str(line.wavelength_angstrom)
                    or query in line.comments.upper()
                    or query in line.multiplet_id.upper()
                    or query in line.line_id.upper()
                    or query in line.transition_name.upper()
                )
            ]

        if filters.element_filter:
            results = [
                line
                for line in results
                if (line.element_symbol or line.element).upper() == filters.element_filter.upper()
            ]

        if filters.charge_state is not None:
            results = [line for line in results if line.charge_state == filters.charge_state]

        if filters.wavelength_min is not None:
            results = [
                line for line in results if line.wavelength_angstrom >= filters.wavelength_min
            ]
        if filters.wavelength_max is not None:
            results = [
                line for line in results if line.wavelength_angstrom <= filters.wavelength_max
            ]

        if filters.multiplet_filter:
            results = [line for line in results if line.multiplet_id == filters.multiplet_filter]
        if filters.only_multiplets:
            results = [
                line for line in results if line.multiplet_id and self.has_multiplet_siblings(line)
            ]

        return sorted(results, key=lambda x: x.wavelength_angstrom)

    def get_available_elements(self) -> list[str]:
        """Return available symbols in atomic-number order.

        Deuterium is placed immediately after hydrogen. Symbols not present in
        the periodic-table mapping are retained after known elements so an
        externally supplied catalog remains searchable.
        """

        def element_order(symbol: str) -> tuple[int, int, int, str]:
            normalized = symbol.upper()
            if normalized == "H":
                return (0, _ELEMENT_ORDER["H"], 0, normalized)
            if normalized == "D":
                return (0, _ELEMENT_ORDER["H"], 1, normalized)
            atomic_number = _ELEMENT_ORDER.get(normalized)
            if atomic_number is not None:
                return (0, atomic_number, 0, normalized)
            return (1, len(_ELEMENT_ORDER) + 1, 0, normalized)

        return sorted(self._element_index.keys(), key=element_order)

    def get_available_charge_states(self, element: str | None = None) -> list[int]:
        """Return sorted list of charge states present in the dataset."""
        lines = self.lines
        if element:
            normalized = element.upper()
            lines = [
                line
                for line in self.lines
                if (line.element_symbol or line.element).upper() == normalized
            ]

        states = {line.charge_state for line in lines if line.charge_state is not None}
        return sorted(states)
