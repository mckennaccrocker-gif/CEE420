"""Scenario depth math: CRS, nodata, length weights, and bridge exclusion."""

from __future__ import annotations

import json

import geopandas as gpd
import pytest
from pyproj import CRS

from geospatial.crs import require_crs
from geospatial.exposure import SCENARIO_PRODUCT
from geospatial.exposure import depth_from_elevations
from geospatial.exposure import illustrative_label
from geospatial.exposure import length_weighted_mean
from geospatial.exposure import sample_elevations
from geospatial.exposure import select_controlling_channel
from geospatial.exposure import summarize_pieces
from geospatial.flood import FloodModelNotAvailable
from geospatial.flood import depth_on_roads
from geospatial.flood_catalog import coverage_against_princeton


THRESHOLDS = [0.10, 0.30]
STAGES = [1.0, 2.0]


def test_unlabeled_depth_call_still_refuses() -> None:
    with pytest.raises(FloodModelNotAvailable):
        depth_on_roads([1.0, 2.0, 3.0])


def test_length_weighted_mean_skips_nodata() -> None:
    # 10 m at 1 m and 30 m at 3 m is 2.5 m, not the unweighted mean of 2 m.
    assert length_weighted_mean([10.0, 30.0], [1.0, 3.0]) == pytest.approx(2.5)
    # A missing piece is left out. It is not depth zero, which would pull the mean to 0.25.
    assert length_weighted_mean([10.0, 30.0], [1.0, None]) == pytest.approx(1.0)
    assert length_weighted_mean([10.0, 10.0], [None, float("nan")]) is None


def test_nodata_cell_is_not_zero_depth() -> None:
    # North-up 2 by 2 grid. Pixel size 1. Origin at the top-left.
    grid = [[5.0, -9999.0], [8.0, 9.0]]
    transform = (1.0, 0.0, 0.0, 0.0, -1.0, 2.0)
    samples = sample_elevations(grid, transform, -9999.0, [0.5, 1.5, 5.0], [1.5, 1.5, 1.5])
    assert samples == [5.0, None, None]
    with pytest.raises(ValueError, match="Nodata"):
        depth_from_elevations(samples[1], 4.0, 1.0)  # type: ignore[arg-type]


def test_bridge_terrain_is_not_reported_as_deck_depth() -> None:
    # The road cell is 9 m below the assumed water surface. A bridge still
    # gets no depth, because this elevation is the ground under the deck.
    result = summarize_pieces(
        is_bridge=True,
        is_tunnel=False,
        piece_length_m=[12.0, 18.0],
        road_elevation_m=[1.0, 1.0],
        channel_elevation_m=[10.0, 10.0],
        channel_distance_m=[5.0, 5.0],
        max_channel_distance_m=500.0,
        stages_m=STAGES,
        thresholds_m=THRESHOLDS,
    )
    assert result["exposure_status"] == "bridge_deck_unmatched"
    assert result["depth_sampled"] is False
    assert result["hurricane_ida_depth"] is False
    assert result["event_time"] is None
    assert result["depth_max_m_stage_2_00"] is None
    assert result["depth_mean_m_stage_2_00"] is None
    assert result["illustrative_label_stage_2_00"] is None
    assert result["length_m_at_or_above_0_30_stage_2_00"] is None


def test_uphill_channel_is_not_used_as_a_water_surface() -> None:
    # The nearest cell is a hillside tributary, 21 m above the road.
    # A lower cell 400 m away is eligible. The depth uses that cell.
    elevation, distance = select_controlling_channel(
        77.0,
        [98.0, 76.5],
        [100.0, 400.0],
        max_channel_distance_m=500.0,
        max_channel_above_road_m=2.0,
    )
    assert elevation == pytest.approx(76.5)
    assert distance == pytest.approx(400.0)
    # Only the hillside cell is in range. The sample stays unmatched.
    elevation, distance = select_controlling_channel(
        77.0,
        [98.0],
        [393.0],
        max_channel_distance_m=500.0,
        max_channel_above_road_m=2.0,
    )
    assert elevation is None
    assert distance is None
    # A bank 1 m above the road is inside the allowance.
    elevation, distance = select_controlling_channel(
        20.0,
        [21.0],
        [15.0],
        max_channel_distance_m=500.0,
        max_channel_above_road_m=2.0,
    )
    assert elevation == pytest.approx(21.0)
    assert depth_from_elevations(20.0, elevation, 2.0) == pytest.approx(3.0)


def test_valid_pieces_are_length_weighted_and_nodata_is_dropped() -> None:
    # 10 m of road at elevation 10 (depth 0 at stage 1, depth 1 at stage 2)
    # and 30 m at elevation 8 (depth 2 at stage 1). One nodata piece of 100 m
    # must not enter the mean. One far piece must not be coded as dry.
    result = summarize_pieces(
        is_bridge=False,
        is_tunnel=False,
        piece_length_m=[10.0, 30.0, 100.0, 7.0],
        road_elevation_m=[10.0, 8.0, None, 0.0],
        channel_elevation_m=[9.0, 9.0, 9.0, 9.0],
        channel_distance_m=[10.0, 10.0, 10.0, 900.0],
        max_channel_distance_m=500.0,
        stages_m=STAGES,
        thresholds_m=THRESHOLDS,
    )
    assert result["n_valid"] == 2
    assert result["n_nodata"] == 1
    assert result["n_outside_channel"] == 1
    assert result["sampled_length_m"] == pytest.approx(40.0)
    # Stage 1 m: depths 0 and 2. Weighted mean (10*0 + 30*2) / 40 = 1.5.
    assert result["depth_mean_m_stage_1_00"] == pytest.approx(1.5)
    assert result["depth_max_m_stage_1_00"] == pytest.approx(2.0)
    assert result["length_m_below_0_10_stage_1_00"] == pytest.approx(10.0)
    assert result["length_m_at_or_above_0_30_stage_1_00"] == pytest.approx(30.0)
    assert result["illustrative_label_stage_1_00"] == "at_or_above_0_30m_preliminary"
    assert illustrative_label(0.2, THRESHOLDS) == "between_0_10m_and_0_30m_preliminary"
    assert result["event_time"] is None


def test_catalogued_extents_do_not_meet_princeton(boundary) -> None:
    records = coverage_against_princeton(boundary)
    assert records
    for record in records:
        assert record["intersects_princeton"] is False
        assert record["used_as_princeton_depth"] is False
        assert record["distance_to_princeton_km"] > 1.0


def test_saved_scenario_outputs(project_root, boundary) -> None:
    stats_path = project_root / "data" / "processed" / "flood_exposure_stats.json"
    if not stats_path.is_file():
        pytest.fail("Scenario stats are missing. Run python3 scripts/flood_exposure.py.")
    stats = json.loads(stats_path.read_text())
    assert stats["hurricane_ida_simulation"] is False
    assert stats["observed_flood_depths_used"] is False
    assert stats["event_time"] is None
    assert stats["product"] == SCENARIO_PRODUCT
    assert stats["thresholds"]["network_disruption_analysis"] is False
    assert stats["thresholds"]["not_closure_standards"] is True
    assert stats["high_water_marks"]["n_inside_boundary"] == 0
    assert stats["high_water_marks"]["used_as_depth_surface"] is False
    assert stats["search"] == "data/processed/flood_raster_search.json"

    dem_path = project_root / "data" / "raw" / "usgs_3dep_princeton_10m.tif"
    import rasterio

    with rasterio.open(dem_path) as dataset:
        require_crs(dataset.crs, "EPSG:26918", "saved 3DEP clip")
        assert dataset.nodata is None or dataset.nodata != 0
        assert CRS.from_user_input(dataset.crs).to_epsg() == 26918

    search = json.loads((project_root / "data" / "processed" / "flood_raster_search.json").read_text())
    assert search["suitable_depth_raster_intersects_princeton"] is False
    recomputed = coverage_against_princeton(boundary)
    by_id = {item["id"]: item for item in recomputed}
    for candidate in search["candidates"]:
        assert candidate["intersects_princeton"] is False
        again = by_id[candidate["id"]]
        assert again["intersects_princeton"] is False
        assert candidate["distance_to_princeton_km"] == pytest.approx(again["distance_to_princeton_km"], rel=1e-6)

    exposure = gpd.read_file(
        project_root / "data" / "processed" / "princeton_centerline_exposure.gpkg",
        layer="centerline_exposure",
    )
    require_crs(exposure.crs, "EPSG:3424", "centerline exposure")
    assert len(exposure) == stats["n_centerlines"]
    assert bool(exposure["hurricane_ida_depth"].any()) is False
    assert exposure["event_time"].isna().all()
    bridges = exposure[exposure["is_bridge"] == True]  # noqa: E712
    assert len(bridges) == stats["bridges_not_sampled"]["n_centerlines"]
    assert (bridges["exposure_status"] == "bridge_deck_unmatched").all()
    assert bridges["depth_max_m_stage_2_00"].isna().all()
    assert bridges["depth_mean_m_stage_1_00"].isna().all()
    # Unmatched decks are not filed under the "below 0.10 m" label.
    assert bridges["illustrative_label_stage_2_00"].isna().all()

    sampled = exposure[exposure["depth_sampled"] == True]  # noqa: E712
    piece_above = float(sampled["length_m_at_or_above_0_30_stage_2_00"].sum())
    assert piece_above == pytest.approx(
        stats["stages"]["2.00"]["piece_length_m_at_or_above_upper_threshold"], rel=1e-6
    )
    weights = sampled["sampled_length_m"].astype(float)
    weighted = float((sampled["depth_mean_m_stage_2_00"] * weights).sum() / weights.sum())
    assert weighted == pytest.approx(stats["stages"]["2.00"]["length_weighted_mean_depth_m"], rel=1e-6)

    geographic = gpd.read_file(project_root / "data" / "processed" / "princeton_centerline_exposure.geojson")
    require_crs(geographic.crs, "EPSG:4326", "exposure geojson")
    map_path = project_root / "outputs" / "maps" / "princeton_scenario_exposure.png"
    assert map_path.read_bytes().startswith(b"\x89PNG")
    assert map_path.stat().st_size > 20_000
