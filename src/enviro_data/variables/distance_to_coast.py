"""Shortest planar WGS84 distance from a point to coastline geometry."""
from ._common import VariableResult, geometry_of, lines, rings, segment_length
from enviro_data.osm_matching import _segment_distance_m

def compute_distance_to_coast(point, coast_candidates):
    lon, lat = point[0], point[1]; best = None; best_id = None
    for candidate in coast_candidates or []:
        geom = geometry_of(candidate); parts = lines(geom) or rings(geom)
        for part in parts:
            for a, b in zip(part, part[1:]):
                d = _segment_distance_m((lon, lat), a, b, lat)
                if best is None or d < best: best, best_id = d, getattr(candidate, "osm_id", None)
    if best is None: return VariableResult(None, "unavailable", {"reason": "coastline_geometry_required"})
    return VariableResult(best, "ok", {"units": "m", "coast_osm_id": best_id})
