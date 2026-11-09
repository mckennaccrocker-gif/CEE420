"""Download and save Princeton's baseline drivable road network.

This is the only analysis script in stage 1. It does not estimate flood depth.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from network.baseline import build_baseline  # noqa: E402


def main() -> None:
    try:
        stats = build_baseline()
    except ImportError as exc:
        missing = exc.name or "a required package"
        raise SystemExit(
            f"Missing dependency {missing!r}. Install stage-1 requirements with:\n"
            "  pip install -r requirements.txt"
        ) from exc
    network = stats["network"]
    print("Princeton baseline drive network")
    print(f"  retrieved_at_utc: {stats['retrieved_at_utc']}")
    print(f"  CRS: {stats['crs']['projected']} ({stats['crs']['projected_name']})")
    print(f"  nodes: {network['n_nodes']}")
    print(f"  intersections (>=2 streets): {network['n_intersections']}")
    print(f"  weakly connected components: {network['n_weakly_connected_components']}")
    print(f"  centerline length inside municipality: {network['centerline_length_inside_m']:.1f} m")
    print(f"  centerline length, full retained segments: {network['centerline_length_m']:.1f} m")
    print(f"  bridge centerlines: {network['n_bridge_centerlines']}")
    print("  flood model: none")
    print(f"  wrote {stats['files']['gpkg']['path']}")
    print(f"  wrote {stats['files']['map_png']['path']}")


if __name__ == "__main__":
    main()
