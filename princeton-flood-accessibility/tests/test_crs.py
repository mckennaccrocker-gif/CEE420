"""CRS conversion and the municipal-boundary identity checks."""

from __future__ import annotations

import json

import pytest
from pyproj import CRS

from geospatial.crs import US_SURVEY_FOOT_M
from geospatial.crs import require_crs
from geospatial.crs import same_crs
from geospatial.crs import us_survey_feet_to_m
from network.roads import validate_princeton_boundary


def test_us_survey_foot_matches_epsg_3424() -> None:
    factor = CRS.from_epsg(3424).axis_info[0].unit_conversion_factor
    assert factor == pytest.approx(1200 / 3937, rel=1e-12)
    assert US_SURVEY_FOOT_M == 1200 / 3937
    assert us_survey_feet_to_m(3937) == pytest.approx(1200)


def test_epsg_3424_is_new_jersey_us_survey_feet() -> None:
    crs = CRS.from_epsg(3424)
    assert "New Jersey" in crs.name
    assert crs.axis_info[0].unit_name == "US survey foot"
    assert same_crs("EPSG:3424", crs)
    require_crs(crs, "EPSG:3424", "state plane")


def test_missing_crs_is_rejected() -> None:
    with pytest.raises(ValueError, match="missing"):
        require_crs(None, "EPSG:3424", "layer")


def test_boundary_is_princeton_new_jersey(boundary, settings) -> None:
    summary = validate_princeton_boundary(boundary, settings)
    assert summary["area_km2_epsg26918"] == pytest.approx(47.66, abs=0.005)
    assert summary["area_km2_epsg3424"] == pytest.approx(summary["area_km2_epsg26918"], abs=0.05)
    assert -74.70 < summary["centroid_lon"] < -74.60
    assert 40.32 < summary["centroid_lat"] < 40.37


def test_boundary_hash_matches_provenance(project_root) -> None:
    import hashlib

    raw = project_root / "data" / "raw" / "princeton_boundary.geojson"
    provenance = json.loads((project_root / "data" / "raw" / "boundary_provenance.json").read_text())
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    assert digest == provenance["sha256"]
    assert provenance["feature_name"] == "Princeton, New Jersey"


def test_wrong_town_is_refused(boundary, settings) -> None:
    impostor = boundary.copy()
    impostor["name"] = "Princeton, West Virginia"
    with pytest.raises(ValueError, match="not Princeton, New Jersey"):
        validate_princeton_boundary(impostor, settings)


def test_depth_thresholds_are_unused_assumptions(settings) -> None:
    assert settings["thresholds"]["depth_m"] == pytest.approx([0.10, 0.30])
    assert settings["thresholds"]["applied_in_stage_1"] is False
    assert settings["crs"]["projected"] == "EPSG:3424"
