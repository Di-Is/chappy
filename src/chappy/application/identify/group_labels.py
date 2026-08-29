"""Display-label derivation for declarative identify groups."""

from __future__ import annotations


def declarative_group_label(*, multiplet_label: str, species: str, tie_group_key: str) -> str:
    """Return the atomic label or a species fallback for a declared group."""
    if multiplet_label:
        return multiplet_label
    if tie_group_key:
        return species
    return ""


__all__ = ["declarative_group_label"]
