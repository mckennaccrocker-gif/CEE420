"""Refuse unlabeled depth calls.

The stage-2 scenario lives in ``geospatial.exposure`` and is started from
``scripts/flood_exposure.py``. It is a labeled hypothetical water surface,
not a Hurricane Ida depth. This function does not return those scenario
depths, so a caller cannot treat them as measurements.
"""


class FloodModelNotAvailable(NotImplementedError):
    """Raised when code asks for a depth without the labeled scenario."""


def depth_on_roads(*_args: object, **_kwargs: object) -> None:
    """Do not return a depth as if it had been measured.

    No Hurricane Ida depth raster whose extent intersects Princeton is in
    this project. The 3DEP channel-relative scenario is a separate,
    explicitly labeled product. This function does not run it and does not
    return its depths.
    """
    raise FloodModelNotAvailable(
        "depth_on_roads does not sample a flood surface. No Hurricane Ida "
        "depth raster intersecting Princeton, NJ is in this project. The "
        "labeled USGS 3DEP scenario is scripts/flood_exposure.py. It is not "
        "an Ida observation, and this function will not return those "
        "scenario depths as measurements."
    )
