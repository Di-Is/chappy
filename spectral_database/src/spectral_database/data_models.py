"""Data models for spectral line records and filter options.

This module defines the core data structures used throughout the package.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LineRecord:
    """Represents a single spectral line with all associated data.

    This dataclass stores comprehensive information about a spectral transition,
    including wavelength, oscillator strength, energy levels, and multiplet grouping.

    Attributes based on spec.md §8 CSV schema.
    """

    line_id: str
    name: str
    species: str
    wavelength: float  # Best wavelength (vacuum, Å) - chosen by smallest uncertainty
    f_value: float
    gamma: float
    element_symbol: str
    charge_state: int
    aki_value: float | None = None
    degeneracy: str | None = None
    transition_type: str | None = None
    lower_level_energy: float | None = None
    upper_level_energy: float | None = None
    wavelength_source: str | None = None  # "ritz" or "observed"
    wavelength_ritz: float | None = None  # Ritz wavelength (vacuum, Å)
    wavelength_ritz_unc: float | None = None  # Ritz uncertainty (Å)
    wavelength_observed: float | None = None  # Observed wavelength (vacuum, Å)
    wavelength_observed_unc: float | None = None  # Observed uncertainty (Å)
    accuracy: str | None = None
    lower_level_conf: str | None = None
    lower_level_term: str | None = None
    lower_level_j: str | None = None
    upper_level_conf: str | None = None
    upper_level_term: str | None = None
    upper_level_j: str | None = None
    upper_term_ls: str | None = None  # Normalized LS term (parity removed)
    comment: str = ""
    # NIST reference codes
    tp_ref: str | None = None  # NIST TP (Transition Probability) reference code
    line_ref: str | None = None  # NIST LINE (wavelength) reference code
    # Multiplet grouping fields (spec.md §5.3)
    absorption_multiplet_id: str | None = None
    multiplet_id: str | None = None  # sha256(canonical_id) for multiplet identification
    # Multiplet metrics (n_components/component_index) are derived on demand per UI/export use case.
    mutiplet_name: str | None = None  # denormalized label like "C IV 1548/1551"
    # Internal fields for processing (not exported)
    _lower_term: str | None = field(default=None, repr=False)
    _upper_term: str | None = field(default=None, repr=False)
    gamma_upper: float | None = None
    gamma_lower: float | None = None


@dataclass
class FilterOptions:
    """Options for filtering spectral lines based on physical properties.

    These filters allow users to select lines based on transition type,
    energy level, and oscillator strength criteria.
    """

    min_f: float | None = None
    max_ei_ev: float | None = None
    allowed_types: set[str] | None = None  # e.g., {"E1"}
    strict_ei: bool = False  # if True, drop rows with missing Ei
    assume_e1_when_missing: bool = False  # treat missing/-- Type as E1 when filtering
    include_principal_only_levels: bool = True  # include rows lacking term/J info


@dataclass
class LineFilterThresholds:
    """Container for oscillator strength / energy thresholds."""

    min_f: float | None = None
    max_ei_ev: float | None = None

    def apply(self, target: FilterOptions, skip_if_set: bool = False) -> None:
        """Apply thresholds to ``target`` in-place.

        Args:
            target: Filter options to mutate.
            skip_if_set: When True, keep existing non-None values on ``target``.
        """
        if self.min_f is not None and (not skip_if_set or target.min_f is None):
            target.min_f = self.min_f
        if self.max_ei_ev is not None and (not skip_if_set or target.max_ei_ev is None):
            target.max_ei_ev = self.max_ei_ev


@dataclass
class SpeciesFilterProfile:
    """Named group of species/element overrides for filter thresholds."""

    name: str | None = None
    species: set[str] = field(default_factory=set)
    elements: set[str] = field(default_factory=set)
    min_f: float | None = None
    max_ei_ev: float | None = None

    def apply(self, target: FilterOptions) -> None:
        """Apply profile thresholds to ``target`` in-place."""
        if self.min_f is not None:
            target.min_f = self.min_f
        if self.max_ei_ev is not None:
            target.max_ei_ev = self.max_ei_ev


def _clone_filter_options(base: FilterOptions) -> FilterOptions:
    allowed_types_copy = set(base.allowed_types) if base.allowed_types is not None else None
    return FilterOptions(
        min_f=base.min_f,
        max_ei_ev=base.max_ei_ev,
        allowed_types=allowed_types_copy,
        strict_ei=base.strict_ei,
        assume_e1_when_missing=base.assume_e1_when_missing,
        include_principal_only_levels=base.include_principal_only_levels,
    )


@dataclass
class SpeciesFilterSet:
    """Collection of defaults and profiles for species-specific filtering."""

    defaults: list[LineFilterThresholds] = field(default_factory=list)
    profiles: list[SpeciesFilterProfile] = field(default_factory=list)

    def merged_with(self, other: SpeciesFilterSet) -> SpeciesFilterSet:
        """Return a new set combining ``self`` and ``other`` preserving order."""
        return SpeciesFilterSet(
            defaults=[*self.defaults, *other.defaults], profiles=[*self.profiles, *other.profiles]
        )

    def resolve(self, base: FilterOptions, species: str) -> FilterOptions:
        """Compute effective filter options for ``species``."""
        result = _clone_filter_options(base)

        for default in self.defaults:
            default.apply(result, skip_if_set=True)

        normalized = species.strip().lower() if species else ""
        if not normalized:
            return result

        element = normalized.split()[0]

        for profile in self.profiles:
            if element and element in profile.elements:
                profile.apply(result)
            if normalized in profile.species:
                profile.apply(result)

        return result


@dataclass
class SpeciesPreset:
    """Container for a single preset definition and its filter set."""

    name: str
    species: list[str] = field(default_factory=list)
    filters: SpeciesFilterSet = field(default_factory=SpeciesFilterSet)
