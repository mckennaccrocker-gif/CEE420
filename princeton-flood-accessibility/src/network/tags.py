"""OSM tag handling for bridges, tunnels, and posted speed.

Missing tags stay missing. Bare maxspeed numbers are not converted, because
OSM's default unit is kilometres per hour except where a local import used
miles per hour without saying so. Only explicit units are parsed.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

# OSM false-like values. Anything else on ``bridge`` (yes, viaduct, movable,
# covered, ...) marks the way as a bridge asset.
_FALSE_VALUES = {"", "no", "false", "0", "none", "nan"}

# International mile, only for tags that already say mph or km/h.
_M_PER_MILE = 1609.344
_M_PER_KM = 1000.0


def iter_tag_values(value: Any) -> Iterator[str]:
    """Flatten a tag that may be missing, a scalar, or a list from simplification."""
    if value is None:
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from iter_tag_values(item)
        return
    if isinstance(value, float) and math.isnan(value):
        return
    text = str(value).strip().lower()
    if text == "nan":
        return
    yield text


def is_bridge_tag(value: Any) -> bool:
    """True when OSM marks any part of the edge as a bridge.

    A simplified edge that mixes bridge and non-bridge pieces is kept as a
    bridge so a later depth sample cannot treat the whole centerline as
    ground level. This flag is not a deck elevation.
    """
    values = list(iter_tag_values(value))
    return any(item not in _FALSE_VALUES for item in values)


def is_tunnel_tag(value: Any) -> bool:
    """True when OSM marks any part of the edge as a tunnel."""
    values = list(iter_tag_values(value))
    return any(item not in _FALSE_VALUES for item in values)


def is_positive_layer(value: Any) -> bool:
    """True when an OSM ``layer`` value is a number greater than zero.

    ``layer>0`` means the way is stacked above another way. It is not proof
    that the deck is above a flood surface, and it is stored separately
    from ``is_bridge``.
    """
    for item in iter_tag_values(value):
        try:
            if float(item) > 0:
                return True
        except ValueError:
            continue
    return False


def parse_explicit_maxspeed_mph(value: Any) -> float | None:
    """Parse a maxspeed tag to miles per hour only when the unit is written.

    Returns None when the tag is missing, mixed, or a bare number. None means
    unknown. It must not be filled in with a default speed.
    """
    values = list(iter_tag_values(value))
    if len(values) != 1:
        return None
    text = values[0].replace(" ", "")
    if text.endswith("mph"):
        return _positive_float(text[: -len("mph")])
    if text.endswith("km/h"):
        kmh = _positive_float(text[: -len("km/h")])
        if kmh is None:
            return None
        return kmh * _M_PER_KM / _M_PER_MILE
    return None


def _positive_float(text: str) -> float | None:
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def collapse_highway(value: Any) -> str:
    """Map an OSM highway tag to a small set of classes for the baseline map."""
    values = list(iter_tag_values(value))
    text = values[0] if values else "other"
    text = text.split(";")[0]
    if text.startswith("motorway") or text.startswith("trunk"):
        return "motorway_trunk"
    for name in ("primary", "secondary", "tertiary", "residential", "service"):
        if text.startswith(name):
            return name
    if text.startswith("unclassified") or text.startswith("living_street"):
        return "residential"
    return "other"
