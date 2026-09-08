"""Length of a waterway line feature in metres."""
from ._common import VariableResult, geometry_of, lines, segment_length

def compute_waterway_length(candidate, reference_latitude=None):
    geom = geometry_of(candidate) if candidate is not None else {}; ls = lines(geom)
    if not ls: return VariableResult(None, "unavailable", {"reason": "line_geometry_required"})
    lat = reference_latitude if reference_latitude is not None else sum(y for l in ls for _, y in l) / sum(len(l) for l in ls)
    return VariableResult(sum(segment_length(a, b, lat) for l in ls for a, b in zip(l, l[1:])), "ok", {"units": "m"})
