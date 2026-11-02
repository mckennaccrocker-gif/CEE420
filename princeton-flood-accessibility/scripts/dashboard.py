"""Later-stage placeholder. Running this does not open a dashboard."""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "dashboard.py is not implemented. Stage 1 has no flood or accessibility "
        "layers to show. The baseline map is outputs/maps/princeton_baseline_drive_network.png "
        "after scripts/download_roads.py."
    )


if __name__ == "__main__":
    main()
