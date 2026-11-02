"""Static before/after map of assumed closures. Not a dashboard."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from geospatial.crs import US_SURVEY_FOOT_M
from network.disruption import STATUS_BRIDGE
from network.disruption import STATUS_CLOSED
from network.disruption import STATUS_NO_CHANNEL


def save_disruption_map(
    boundary: gpd.GeoDataFrame,
    centerlines: gpd.GeoDataFrame,
    *,
    stages_m: list[float],
    path: Path,
) -> None:
    """One panel per assumed stage, plus the uncut network.

    Red is the fraction-rule closure. Purple stays in the graph because the
    deck depth is unknown. Gray roads with no channel match also stay in.
    """
    if centerlines.crs is None or boundary.crs is None:
        raise ValueError("Disruption map inputs are missing a CRS.")
    municipal = boundary.to_crs(centerlines.crs)
    n_panels = 1 + len(stages_m)
    figure, axes = plt.subplots(1, n_panels, figsize=(4.6 * n_panels, 8.2), sharex=True, sharey=True)
    if n_panels == 1:
        axes = [axes]
    panels: list[tuple[object, str]] = [(None, "Baseline network\nNo centerlines removed")]
    for stage in stages_m:
        slug = f"{stage:.2f}".replace(".", "_")
        panels.append((f"routing_status_stage_{slug}", f"+{stage:.1f} m scenario\nFraction-rule closures in red"))
    for axis, (column, title) in zip(axes, panels, strict=True):
        municipal.boundary.plot(ax=axis, color="#222222", linewidth=0.7)
        if column is None:
            centerlines.plot(ax=axis, color="#6b6b6b", linewidth=0.45)
        else:
            _draw_status(axis, centerlines, column)
        axis.set_title(title, fontsize=10)
        axis.set_axis_off()
        _scale_bar(axis)
    axes[0].legend(
        handles=[
            Line2D([0], [0], color="#6b6b6b", linewidth=2, label="Routable, scenario depth below the closure rule"),
            Line2D([0], [0], color="#bdbdbd", linewidth=2, label="No channel match, still routable"),
            Line2D([0], [0], color="#54278f", linewidth=2, label="Bridge deck unmatched, still routable"),
            Line2D([0], [0], color="#d94801", linewidth=2, label="Assumed closed (fraction rule)"),
        ],
        loc="lower left",
        fontsize=7,
        frameon=True,
    )
    figure.suptitle(
        "Hypothetical 3DEP scenario. Not Hurricane Ida.\n"
        "Red roads are removed under a preliminary fraction rule, not a closure standard.",
        fontsize=11,
    )
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=140, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def _draw_status(axis, centerlines: gpd.GeoDataFrame, column: str) -> None:
    status = centerlines[column]
    closed = centerlines[status == STATUS_CLOSED]
    bridges = centerlines[status == STATUS_BRIDGE]
    unmatched = centerlines[status == STATUS_NO_CHANNEL]
    other = centerlines[~status.isin([STATUS_CLOSED, STATUS_BRIDGE, STATUS_NO_CHANNEL])]
    if not unmatched.empty:
        unmatched.plot(ax=axis, color="#bdbdbd", linewidth=0.4)
    if not other.empty:
        other.plot(ax=axis, color="#6b6b6b", linewidth=0.45)
    if not bridges.empty:
        bridges.plot(ax=axis, color="#54278f", linewidth=1.1)
    if not closed.empty:
        closed.plot(ax=axis, color="#d94801", linewidth=1.15)


def _scale_bar(axis) -> None:
    length_ftus = 2000.0 / US_SURVEY_FOOT_M
    x0, x1 = axis.get_xlim()
    y0, y1 = axis.get_ylim()
    start_x = x0 + 0.08 * (x1 - x0)
    start_y = y0 + 0.06 * (y1 - y0)
    axis.plot([start_x, start_x + length_ftus], [start_y, start_y], color="#111111", linewidth=2.0, solid_capstyle="butt")
    axis.text(start_x, start_y + 0.012 * (y1 - y0), "2 km", ha="left", va="bottom", fontsize=8)
