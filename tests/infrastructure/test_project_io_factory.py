"""Tests for lightweight default project-I/O composition."""

from __future__ import annotations

import subprocess
import sys


def test_default_factory_construction_does_not_import_h5py() -> None:
    """Constructing the use case must not initialize the HDF5 implementation."""
    script = """
import sys
from chappy.infrastructure.project_io_factory import create_default_project_io_usecase

create_default_project_io_usecase()
assert "h5py" not in sys.modules
assert "chappy.infrastructure.hdf5_project_repository" not in sys.modules
"""

    result = subprocess.run(
        [sys.executable, "-c", script], check=False, capture_output=True, text=True, timeout=15
    )

    assert result.returncode == 0, result.stderr
