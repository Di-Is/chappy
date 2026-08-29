"""Tests for stable line identifier construction."""

from __future__ import annotations

import re

from spectral_database.filters import build_line_id


def test_build_line_id_matches_expected_digest() -> None:
    """Ensure canonical inputs produce the frozen hash value."""
    line_id = build_line_id(
        element="C",
        charge=3,
        lower_conf="1s2.2s",
        lower_term="2S",
        lower_j="1/2",
        lower_raw="1s2.2s|2S|1/2",
        upper_conf="1s2.2p",
        upper_term="2P*",
        upper_j="3/2",
        upper_raw="1s2.2p|2P*|3/2",
    )

    assert line_id == "703f975612c284c7"


def test_build_line_id_ignores_parity_markers() -> None:
    """Parity symbol variations should not change the identifier."""
    legacy = build_line_id(
        element="C",
        charge=3,
        lower_conf="1s2.2s",
        lower_term="2S",
        lower_j="1/2",
        lower_raw="1s2.2s|2S|1/2",
        upper_conf="1s2.2p",
        upper_term="2P*",
        upper_j="3/2",
        upper_raw="1s2.2p|2P*|3/2",
    )
    updated = build_line_id(
        element="C",
        charge=3,
        lower_conf="1s2.2s",
        lower_term="2S",
        lower_j="1/2",
        lower_raw="1s2.2s|2S|1/2",
        upper_conf="1s2.2p",
        upper_term="2P°",
        upper_j="3/2",
        upper_raw="1s2.2p|2P°|3/2",
    )

    assert legacy == updated == "703f975612c284c7"


def test_build_line_id_remains_hex_even_without_level_data() -> None:
    """Fallback path should still emit a 16-digit lowercase hex value."""
    line_id = build_line_id(
        element="H",
        charge=0,
        lower_conf=None,
        lower_term=None,
        lower_j=None,
        lower_raw=None,
        upper_conf=None,
        upper_term=None,
        upper_j=None,
        upper_raw=None,
    )

    assert re.fullmatch(r"[0-9a-f]{16}", line_id)
