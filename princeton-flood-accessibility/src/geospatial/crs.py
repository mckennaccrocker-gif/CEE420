"""Coordinate reference systems used for the Princeton road network.

EPSG:3424 is NAD83 / New Jersey (ftUS). Distances in that CRS are US survey
feet. Convert to metres with the exact definition 1 ftUS = 1200/3937 m.
Do not use the international foot (0.3048 m).
"""

from __future__ import annotations

from pyproj import CRS

# Exact US survey foot. The decimal from CRS.axis_info is the same value
# up to floating-point noise; tests check that.
US_SURVEY_FOOT_M = 1200 / 3937

PROJECTED_EPSG = 3424
GEOGRAPHIC_EPSG = 4326
AREA_CHECK_EPSG = 26918


def us_survey_feet_to_m(length_ftus: float) -> float:
    """Convert a planar length in US survey feet to metres."""
    return float(length_ftus) * US_SURVEY_FOOT_M


def crs_epsg(crs: CRS | str | int) -> CRS:
    """Return a pyproj CRS, accepting an EPSG code or an existing CRS."""
    if isinstance(crs, CRS):
        return crs
    return CRS.from_user_input(crs)


def same_crs(left: CRS | str | int | None, right: CRS | str | int) -> bool:
    """True when both CRS objects describe the same system.

    A missing CRS is never treated as a match. Comparing with ``equals``
    accepts equivalent WKT and EPSG spellings of EPSG:3424.
    """
    if left is None:
        return False
    return crs_epsg(left).equals(crs_epsg(right))


def require_crs(crs: CRS | str | int | None, expected: CRS | str | int, label: str) -> None:
    """Raise if ``crs`` is missing or is not ``expected``."""
    if not same_crs(crs, expected):
        found = "missing" if crs is None else str(crs)
        raise ValueError(f"{label} CRS is {found}; expected {expected}.")


def proj_pipeline(from_crs: str, to_crs: str) -> str:
    """PROJ pipeline used to transform coordinates, recorded for provenance."""
    from pyproj import Transformer

    transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
    return transformer.to_proj4()
