"""Perimeter of polygon water features in metres."""
from ._common import VariableResult, geometry_of, rings, segment_length

def compute_water_perimeter(candidate, reference_latitude=None):
    geom = geometry_of(candidate) if candidate is not None else {}; rs = rings(geom)
    if not rs: return VariableResult(None, "unavailable", {"reason": "polygon_geometry_required"})
    lat = reference_latitude if reference_latitude is not None else sum(y for r in rs for _, y in r) / sum(len(r) for r in rs)
    return VariableResult(sum(segment_length(a, b, lat) for r in rs for a, b in zip(r, r[1:])), "ok", {"units": "m"})
