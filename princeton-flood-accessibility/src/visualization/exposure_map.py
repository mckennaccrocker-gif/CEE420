"""Static map of the labeled 3DEP scenario. Not a dashboard and not an Ida map."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from geospatial.crs import US_SURVEY_FOOT_M
from geospatial.exposure import STATUS_BRIDGE
from geospatial.exposure import STATUS_NODATA
from geospatial.exposure import STATUS_OUTSIDE_CHANNEL
from geospatial.exposure import STATUS_OUTSIDE_TOWN
from geospatial.exposure import STATUS_TUNNEL


def save_exposure_map(
    boundary: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    *,
    primary_stage_m: float,
    label_column: str,
    path: Path,
) -> None:
    """Color each centerline by its maximum-sample label at one assumed stage.

    Bridge decks stay a separate class. They are not drawn as dry or flooded.
    """
    if centerlines.crs is None or boundary.crs is None:
        raise ValueError("Exposure map inputs are missing a CRS.")
    municipal = boundary.to_crs(centerlines.crs)
    figure, axis = plt.subplots(figsize=(8.4, 8.6))
    municipal.boundary.plot(ax=axis, color="#222222", linewidth=0.8)

    def _subset(status: str) -> gpd.GeoDataFrame:
        return centerlines[centerlines["exposure_status"] == status]

    draw_order = [
        (STATUS_OUTSIDE_TOWN, "#f0f0f0", "Outside the municipality"),
        (STATUS_OUTSIDE_CHANNEL, "#bdbdbd", "No channel within the distance cap"),
        (STATUS_NODATA, "#636363", "DEM nodata"),
        ("below", "#9ecae1", "Max depth below 0.10 m"),
        ("between", "#fe9929", "Max depth 0.10 m to below 0.30 m"),
        ("above", "#d94801", "Max depth at or above 0.30 m"),
        (STATUS_TUNNEL, "#6a3d9a", "Tunnel, unmatched"),
        (STATUS_BRIDGE, "#54278f", "Bridge deck, unmatched"),
    ]
    present: list[tuple[str, str]] = []
    depth_rows = centerlines[centerlines["exposure_status"] == "scenario_depth"]
    for key, color, legend in draw_order:
        if key == "below":
            frame = depth_rows[depth_rows[label_column].astype(str).str.startswith("below_")]
        elif key == "between":
            frame = depth_rows[depth_rows[label_column].astype(str).str.startswith("between_")]
        elif key == "above":
            frame = depth_rows[depth_rows[label_column].astype(str).str.startswith("at_or_above_")]
        else:
            frame = _subset(key)
        if frame.empty:
            continue
        linewidth = 1.6 if key in {STATUS_BRIDGE, "above"} else 0.7
        frame.plot(ax=axis, color=color, linewidth=linewidth)
        present.append((color, legend))

    axis.set_title(
        f"Hypothetical 3DEP scenario, +{primary_stage_m:.1f} m above the channel DEM\n"
        "Not a Hurricane Ida simulation. Color is the centerline maximum, not a closure.",
        fontsize=11,
        pad=12,
    )
    axis.set_axis_off()
    handles = [Line2D([0], [0], color=color, linewidth=2.2, label=legend) for color, legend in present]
    axis.legend(handles=handles, loc="lower right", frameon=True, fontsize=8, title="Preliminary labels")
    _scale_bar(axis)
    axis.annotate(
        "N",
        xy=(0.94, 0.90),
        xytext=(0.94, 0.82),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=9,
        arrowprops={"arrowstyle": "-|>", "color": "#111111", "lw": 1.2},
    )
    axis.annotate(
        "Scenario only. 0.10 m and 0.30 m are preliminary assumptions, not closure standards. "
        "Bridge color means the deck was not sampled.",
        xy=(0.0, -0.02),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=7,
        color="#333333",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _scale_bar(axis: plt.Axes) -> None:
    length_ftus = 2000.0 / US_SURVEY_FOOT_M
    x0, x1 = axis.get_xlim()
    y0, y1 = axis.get_ylim()
    start_x = x0 + 0.08 * (x1 - x0)
    start_y = y0 + 0.08 * (y1 - y0)
    axis.plot([start_x, start_x + length_ftus], [start_y, start_y], color="#111111", linewidth=2.0, solid_capstyle="butt")
    axis.text(start_x, start_y + 0.012 * (y1 - y0), "2 km", ha="left", va="bottom", fontsize=8)
