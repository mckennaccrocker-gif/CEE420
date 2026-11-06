"""Shared paths for the stage-1 tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import geopandas as gpd

from network.roads import load_settings


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def settings() -> dict:
    return load_settings(ROOT / "config" / "settings.yaml")


@pytest.fixture(scope="session")
def boundary() -> gpd.GeoDataFrame:
    path = ROOT / "data" / "raw" / "princeton_boundary.geojson"
    frame = gpd.read_file(path)
    return frame
