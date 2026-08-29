"""Typed display commands for the shared spectrum plot boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpectrumPlotDisplayCommand:
    """Describe caller-owned spectrum plot display policy.

    Attributes:
        use_normalized_observed: Whether the observed curve should use the
            continuum-normalized series when available.
        render_absorption_line_labels: Whether absorption-line overlay labels
            should be rendered.
        show_error_spectrum: Whether the observed error curve should be rendered.
        show_component_profiles: Whether per-component profile curves should be
            rendered alongside the composite model curve.
    """

    use_normalized_observed: bool
    render_absorption_line_labels: bool
    show_error_spectrum: bool = True
    show_component_profiles: bool = False
