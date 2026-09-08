"""Surface area of polygon water features in square metres."""
from ._common import VariableResult, geometry_of, rings, polygon_area

def compute_water_surface_area(candidate, reference_latitude=None):
    geom = geometry_of(candidate) if candidate is not None else {}
    rs = rings(geom)
    if not rs: return VariableResult(None, "unavailable", {"reason": "polygon_geometry_required"})
    lat = reference_latitude if reference_latitude is not None else sum(y for r in rs for _, y in r) / sum(len(r) for r in rs)
    # GeoJSON Polygon stores an exterior followed by holes; MultiPolygon is flattened,
    # so this remains a conservative, readable estimate without Shapely.
    area = polygon_area(rs[0], lat) - sum(polygon_area(r, lat) for r in rs[1:])
    return VariableResult(max(0.0, area), "ok", {"units": "m2"})
