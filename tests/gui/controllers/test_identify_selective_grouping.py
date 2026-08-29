"""Tests for selective registration behavior in identify mode.

Users can select specific temporary lines for registration instead of
processing all lines at once.
"""

from __future__ import annotations

import pytest

from chappy.core.identify_state import IdentifySessionState, CandidateLineContext


class TestSelectiveGrouping:
    """Tests for selected-id filtering ahead of registration."""

    @pytest.fixture
    def session_with_systems(self) -> IdentifySessionState:
        """Create session with 3 temporary systems for testing."""
        session = IdentifySessionState()
        # Add 3 systems with different wavelengths
        session.add_candidate_line(
            "C IV",
            1548.0,
            1549.0,
            creation_method="manual",
            context=CandidateLineContext(
                line_id="test_civ_1548",
                rest_wavelength=1548.195,
                multiplet_id="",
                multiplet_label="",
                transition_name="C IV 1548.2",
                oscillator_strength=0.1,
                gamma_value=1e8,
                tie_group_key="",
            ),
        )
        session.add_candidate_line(
            "Si II",
            1526.0,
            1527.0,
            creation_method="manual",
            context=CandidateLineContext(
                line_id="test_sii_1526",
                rest_wavelength=1526.707,
                multiplet_id="",
                multiplet_label="",
                transition_name="Si II 1526.7",
                oscillator_strength=0.1,
                gamma_value=1e8,
                tie_group_key="",
            ),
        )
        session.add_candidate_line(
            "O I",
            1302.0,
            1303.0,
            creation_method="manual",
            context=CandidateLineContext(
                line_id="test_oi_1302",
                rest_wavelength=1302.168,
                multiplet_id="",
                multiplet_label="",
                transition_name="O I 1302.2",
                oscillator_strength=0.1,
                gamma_value=1e8,
                tie_group_key="",
            ),
        )
        return session

    def test_session_has_three_temporary_systems(
        self, session_with_systems: IdentifySessionState
    ) -> None:
        """Verify test fixture creates expected systems."""
        assert len(session_with_systems.candidate_lines) == 3

    def test_filtering_by_selected_ids(self, session_with_systems: IdentifySessionState) -> None:
        """Test that selected_ids filter correctly reduces target systems."""
        systems = session_with_systems.candidate_lines
        all_ids = [s.system_id for s in systems]

        # Select only first two systems
        selected_ids = all_ids[:2]
        selected_set = set(selected_ids)
        target_systems = [s for s in systems if s.system_id in selected_set]

        assert len(target_systems) == 2
        assert target_systems[0].species == "C IV"
        assert target_systems[1].species == "Si II"

    def test_empty_selected_ids_uses_all_systems(
        self, session_with_systems: IdentifySessionState
    ) -> None:
        """Test that empty selected_ids results in using all systems."""
        systems = session_with_systems.candidate_lines
        selected_ids: list[str] = []  # Empty list

        if selected_ids:
            target_systems = [s for s in systems if s.system_id in set(selected_ids)]
        else:
            target_systems = list(systems)

        assert len(target_systems) == 3


class TestSelectiveRemoval:
    """Tests for selective candidate removal after partial registration."""

    @pytest.fixture
    def session_with_four_systems(self) -> IdentifySessionState:
        """Create session with 4 temporary systems."""
        session = IdentifySessionState()
        for name, rest in (
            ("C IV", 1548.195),
            ("Si II", 1526.707),
            ("O I", 1302.168),
            ("Mg II", 2796.0),
        ):
            session.add_candidate_line(
                name,
                rest - 0.5,
                rest + 0.5,
                creation_method="manual",
                context=CandidateLineContext(
                    line_id=f"test_{name.replace(' ', '').lower()}",
                    rest_wavelength=rest,
                    multiplet_id="",
                    multiplet_label="",
                    transition_name=f"{name} {rest:.1f}",
                    oscillator_strength=0.1,
                    gamma_value=1e8,
                    tie_group_key="",
                ),
            )
        return session

    def test_selective_removal_preserves_non_selected(
        self, session_with_four_systems: IdentifySessionState
    ) -> None:
        """Removing registered systems preserves the unselected ones."""
        session = session_with_four_systems
        all_ids = [system.system_id for system in session.candidate_lines]
        registered_ids = set(all_ids[:2])

        session.remove_candidate_lines(registered_ids)

        remaining_ids = {system.system_id for system in session.candidate_lines}
        assert len(remaining_ids) == 2
        assert remaining_ids.isdisjoint(registered_ids)
