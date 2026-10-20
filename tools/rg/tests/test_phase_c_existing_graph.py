"""Mandatory real-store prerequisites for Phase C's existing-graph regression suite.

These tests intentionally do not use the optional ``requires_oxigraph`` marker: the C.1
acceptance scenarios exercise the built extractor and a real pinned store on every CI runner.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def require_real_store_tools():
    dotnet = shutil.which("dotnet")
    oxigraph = shutil.which("oxigraph")
    if not dotnet or not oxigraph:
        pytest.fail("Phase C existing-graph tests require dotnet and oxigraph on PATH.")
    version = subprocess.run([oxigraph, "--version"], check=True, capture_output=True, text=True).stdout
    if "0.5.8" not in version:
        pytest.fail(f"Phase C existing-graph tests require Oxigraph 0.5.8, got: {version.strip()}")


def test_real_store_prerequisites_are_pinned():
    """Keep this module mandatory even while its source/DLL fixture scenarios grow."""
