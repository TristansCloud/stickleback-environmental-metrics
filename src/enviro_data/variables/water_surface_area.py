"""Legacy planar polygon area estimate in square metres.

MultiPolygon exteriors are flattened with holes by this implementation, so
multi-part areas are not reliable. The lake-polygon pilot has a separate
whole-object metric path; see docs/repository_maintenance.md before reuse.
"""

from ._common import VariableResult, geometry_of, rings, polygon_area


def compute_water_surface_area(candidate, reference_latitude=None):
    geom = geometry_of(candidate) if candidate is not None else {}
    rs = rings(geom)
    if not rs:
        return VariableResult(
            None, "unavailable", {"reason": "polygon_geometry_required"}
        )
    lat = (
        reference_latitude
        if reference_latitude is not None
        else sum(y for r in rs for _, y in r) / sum(len(r) for r in rs)
    )
    # This subtraction is valid for a single Polygon, whose first ring is its
    # exterior. Flattening a MultiPolygon loses that exterior/hole distinction.
    area = polygon_area(rs[0], lat) - sum(polygon_area(r, lat) for r in rs[1:])
    return VariableResult(max(0.0, area), "ok", {"units": "m2"})
