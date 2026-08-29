"""Scenario implementations for user-facing operation flows."""

from chappy_user_manual_generator.scenarios.analysis_detail import analysis_region_detail_workflow
from chappy_user_manual_generator.scenarios.analysis_structure import analysis_structure_guide
from chappy_user_manual_generator.scenarios.continuum import continuum_adjustment
from chappy_user_manual_generator.scenarios.identify import identify_candidate_workflow
from chappy_user_manual_generator.scenarios.start import start_data_import

__all__ = [
    "analysis_region_detail_workflow",
    "analysis_structure_guide",
    "continuum_adjustment",
    "identify_candidate_workflow",
    "start_data_import",
]
