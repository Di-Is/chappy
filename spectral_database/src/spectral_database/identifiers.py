"""Canonical identifier helpers for spectral transitions.

This module centralizes normalization routines shared between line and
multiplet identifiers so that hash construction stays consistent even
if upstream NIST tables tweak formatting.
"""

from __future__ import annotations

import hashlib
import re
from fractions import Fraction
from typing import Final

_PLACEHOLDER_TOKENS: Final[set[str]] = {"--", "-", "—"}


def truncate_sha256(value: str, length: int = 16) -> str:
    """Return the leading ``length`` hex characters of a SHA-256 digest."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:length]


def normalize_configuration(conf: str | None) -> str | None:
    """Canonicalize electron configuration strings.

    Removes whitespace and treats placeholder tokens as missing values.
    """
    if not conf:
        return None
    text = str(conf).strip()
    if not text or text in _PLACEHOLDER_TOKENS:
        return None
    collapsed = re.sub(r"\s+", "", text)
    return collapsed or None


def normalize_term(term: str | None) -> str | None:
    """Canonicalize LS term labels by stripping prefixes and parity marks."""
    if not term:
        return None
    stripped = str(term).strip()
    if not stripped or stripped in _PLACEHOLDER_TOKENS:
        return None
    without_prefix = re.sub(r"^[a-z]+", "", stripped, flags=re.IGNORECASE)
    normalized = (
        without_prefix.replace("^o", "°").replace("^O", "°").replace("*", "°").replace("'", "°")
    )
    normalized = normalized.replace("°", "")
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.upper() if normalized else None


def normalize_j(j_str: str | None) -> str | None:
    """Normalize J quantum numbers to fractional or integer notation."""
    if not j_str:
        return None
    text = str(j_str).strip().replace("J=", "").replace("j=", "").strip()
    if not text or text in _PLACEHOLDER_TOKENS:
        return None
    try:
        if "/" in text:
            num, den = text.split("/", 1)
            num_i = int(num.strip())
            den_i = int(den.strip())
            if den_i != 0:
                return f"{num_i}/{den_i}"
        value_f = float(text)
    except (ValueError, TypeError):
        compact = re.sub(r"\s+", "", text)
        return compact or None
    fraction = Fraction(value_f).limit_denominator(16)
    if fraction.denominator == 1:
        return str(fraction.numerator)
    return f"{fraction.numerator}/{fraction.denominator}"


def sanitize_level_text(level: str | None) -> str | None:
    """Produce a compact fallback representation for raw level strings."""
    if not level:
        return None
    text = str(level).strip()
    if not text or text in _PLACEHOLDER_TOKENS:
        return None
    # Collapse whitespace and replace separators that interfere with our delimiters.
    collapsed = re.sub(r"\s+", "", text)
    collapsed = collapsed.replace("|", "/")
    return collapsed or None


def canonical_level_key(
    conf: str | None, term: str | None, j: str | None, raw_level: str | None
) -> str | None:
    """Build a canonical key for an energy level.

    Returns ``None`` only when every input is missing.
    """
    conf_norm = normalize_configuration(conf)
    term_norm = normalize_term(term)
    j_norm = normalize_j(j)
    fallback = sanitize_level_text(raw_level)

    parts: list[str] = []
    if conf_norm:
        parts.append(conf_norm)
    if term_norm:
        parts.append(term_norm)
    if j_norm:
        parts.append(f"J={j_norm}")
    if parts:
        return "|".join(parts)
    if fallback:
        return f"RAW={fallback}"
    return None


def canonical_line_string(  # noqa: PLR0913
    element_symbol: str,
    charge_state: int,
    lower_conf: str | None,
    lower_term: str | None,
    lower_j: str | None,
    lower_raw: str | None,
    upper_conf: str | None,
    upper_term: str | None,
    upper_j: str | None,
    upper_raw: str | None,
) -> str:
    """Compose a canonical string describing a spectral transition."""
    species_key = f"{element_symbol}:{charge_state}"
    lower_key = canonical_level_key(lower_conf, lower_term, lower_j, lower_raw)
    upper_key = canonical_level_key(upper_conf, upper_term, upper_j, upper_raw)

    if lower_key is None:
        lower_key = f"RAW={sanitize_level_text(lower_raw) or '?'}"
    if upper_key is None:
        upper_key = f"RAW={sanitize_level_text(upper_raw) or '?'}"

    return f"{species_key}|{lower_key}->{upper_key}"


def hashed_line_id(**kwargs: str | int | None) -> str:
    """Shortcut to build the stable line identifier from transition fields."""
    canonical = canonical_line_string(**kwargs)  # type: ignore[arg-type]
    return truncate_sha256(canonical)
