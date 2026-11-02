"""Flood exposure is intentionally not implemented in stage 1."""


class FloodModelNotAvailable(NotImplementedError):
    """Raised when flood code is called before a depth surface exists."""


def depth_on_roads(*_args: object, **_kwargs: object) -> None:
    """Do not invent depths.

    No Hurricane Ida depth raster covering Princeton is in this project.
    A bare-earth bathtub on a DEM would be a scenario, not an Ida
    reconstruction, and it has not been run.
    """
    raise FloodModelNotAvailable(
        "No flood-depth model is implemented. Stage 1 did not find a "
        "Hurricane Ida depth raster whose extent intersects Princeton, NJ. "
        "A DEM bathtub would be a hypothetical scenario, not a validated "
        "Ida simulation, and this function does not run one."
    )
