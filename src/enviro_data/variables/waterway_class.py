"""Normalized waterway class from OSM waterway tags."""
from ._common import VariableResult, tags_of

_CLASSES = {"river", "stream", "canal", "drain", "ditch", "brook", "tidal_channel"}
def compute_waterway_class(candidate):
    value = str(tags_of(candidate).get("waterway", "")).lower()
    return VariableResult(value if value in _CLASSES else None, "ok" if value in _CLASSES else "unavailable", {"reason": "waterway_tag_missing"} if value not in _CLASSES else {})
