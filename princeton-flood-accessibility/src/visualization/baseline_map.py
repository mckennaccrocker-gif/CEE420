"""Draw the baseline drivable network. The figure is not a flood map."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from geospatial.crs import US_SURVEY_FOOT_M

# Draw minor roads first so arterial roads stay visible.
_CLASS_STYLE: dict[str, tuple[str, float, str]] = {
    "service": ("#bdbdbd", 0.35, "Service"),
    "other": ("#969696", 0.45, "Other drivable"),
    "residential": ("#737373", 0.55, "Residential"),
    "tertiary": ("#1b9e77", 0.75, "Tertiary"),
    "secondary": ("#7570b3", 0.95, "Secondary"),
    "primary": ("#d95f02", 1.15, "Primary"),
    "motorway_trunk": ("#1a1a1a", 1.45, "Motorway / trunk"),
}
_DRAW_ORDER = [
    "service",
    "other",
    "residential",
    "tertiary",
    "secondary",
    "primary",
    "motorway_trunk",
]


def save_baseline_map(
    boundary: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    stats: dict[str, float | int],
    path: Path,
) -> None:
    """Save a static map of the projected centerlines and the municipal outline.

    Both layers must already be in EPSG:3424. The scale bar uses that CRS:
    2 km is converted to US survey feet with 1200/3937. Bridge features are
    drawn from the OSM ``is_bridge`` flag. Red does not mean flooded.
    """
    if boundary.crs is None or centerlines.crs is None:
        raise ValueError("Map layers are missing a CRS.")
    if not boundary.crs.equals(centerlines.crs):
        raise ValueError(
            f"Map CRS mismatch: boundary is {boundary.crs}, centerlines are {centerlines.crs}."
        )

    figure, axis = plt.subplots(figsize=(11, 12))
    boundary.plot(ax=axis, facecolor="#f4f4f4", edgecolor="#111111", linewidth=0.8, zorder=1)
    present: list[str] = []
    for road_class in _DRAW_ORDER:
        subset = centerlines[centerlines["road_class"] == road_class]
        if subset.empty:
            continue
        color, width, _label = _CLASS_STYLE[road_class]
        subset.plot(ax=axis, color=color, linewidth=width, zorder=2)
        present.append(road_class)
    bridges = centerlines[centerlines["is_bridge"] == True]  # noqa: E712
    if not bridges.empty:
        bridges.plot(ax=axis, color="#e31a1c", linewidth=1.6, zorder=3)
    boundary.boundary.plot(ax=axis, color="#111111", linewidth=0.9, zorder=4)

    _scale_bar(axis, length_km=2.0)
    _north_arrow(axis)
    length_km = float(stats["centerline_length_inside_km"])
    # One title block. A second text artist at y=1.01 sat on top of set_title.
    axis.set_title(
        "Princeton, NJ — baseline drivable road network\n"
        "OpenStreetMap drive network in EPSG:3424 (NAD83 / New Jersey, US survey feet)\n"
        "Not a flood map. Red marks an OSM bridge tag, not inundation.",
        loc="left",
        fontsize=11,
        pad=12,
    )
    axis.text(
        0.02,
        0.02,
        f"Centerline inside the municipality: {length_km:.2f} km\n"
        f"Intersections: {int(stats['n_intersections'])}\n"
        f"Weakly connected components: {int(stats['n_components'])}",
        transform=axis.transAxes,
        ha="left",
        va="bottom",
        fontsize=8,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.92},
    )
    handles = [
        Line2D([0], [0], color=_CLASS_STYLE[name][0], linewidth=_CLASS_STYLE[name][1] + 1.0, label=_CLASS_STYLE[name][2])
        for name in present
    ]
    if not bridges.empty:
        handles.append(Line2D([0], [0], color="#e31a1c", linewidth=2.0, label="Bridge (OSM tag)"))
    axis.legend(handles=handles, loc="lower right", frameon=True, fontsize=8, title="Road class")
    axis.set_axis_off()
    axis.annotate(
        "© OpenStreetMap contributors (ODbL). Municipal boundary: NJGIN public record.",
        xy=(0.0, -0.02),
        xycoords="axes fraction",
        ha="left",
        va="top",
        fontsize=7,
        color="#444444",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _scale_bar(axis: plt.Axes, *, length_km: float) -> None:
    """Draw a scale bar in axis coordinates that are US survey feet."""
    length_ftus = (length_km * 1000.0) / US_SURVEY_FOOT_M
    x0, x1 = axis.get_xlim()
    y0, y1 = axis.get_ylim()
    start_x = x0 + 0.08 * (x1 - x0)
    start_y = y0 + 0.08 * (y1 - y0)
    axis.plot([start_x, start_x + length_ftus], [start_y, start_y], color="#111111", linewidth=2.0, solid_capstyle="butt")
    axis.plot([start_x, start_x], [start_y - 0.004 * (y1 - y0), start_y + 0.004 * (y1 - y0)], color="#111111", linewidth=1.2)
    axis.plot(
        [start_x + length_ftus, start_x + length_ftus],
        [start_y - 0.004 * (y1 - y0), start_y + 0.004 * (y1 - y0)],
        color="#111111",
        linewidth=1.2,
    )
    axis.text(start_x, start_y + 0.012 * (y1 - y0), f"{length_km:.0f} km", ha="left", va="bottom", fontsize=8)


def _north_arrow(axis: plt.Axes) -> None:
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
