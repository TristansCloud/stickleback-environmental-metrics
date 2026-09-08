"""Small dependency-free geometry and result helpers for OSM variables."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Mapping

@dataclass(frozen=True)
class VariableResult:
    value: Any = None
    status: str = "ok"
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    def as_dict(self):
        return {"value": self.value, "status": self.status, "diagnostics": dict(self.diagnostics)}

def rings(geometry):
    typ, c = geometry.get("type"), geometry.get("coordinates", [])
    if typ == "Polygon": return [[(float(x), float(y)) for x, y, *_ in r] for r in c]
    if typ == "MultiPolygon": return [[(float(x), float(y)) for x, y, *_ in r] for p in c for r in p]
    return []

def lines(geometry):
    typ, c = geometry.get("type"), geometry.get("coordinates", [])
    if typ == "LineString": return [[(float(x), float(y)) for x, y, *_ in c]]
    if typ == "MultiLineString": return [[(float(x), float(y)) for x, y, *_ in l] for l in c]
    return []

def meters_per_degree(lat):
    return 111320.0, 111320.0 * math.cos(math.radians(lat))

def polygon_area(ring, lat):
    ky, kx = meters_per_degree(lat); return abs(sum((x1*kx)*(y2*ky)-(x2*kx)*(y1*ky) for (x1,y1),(x2,y2) in zip(ring, ring[1:])))/2

def segment_length(a, b, lat):
    ky, kx = meters_per_degree(lat); return math.hypot((b[0]-a[0])*kx, (b[1]-a[1])*ky)

def geometry_of(value):
    return value.geometry if hasattr(value, "geometry") else value

def tags_of(value):
    return value.tags if hasattr(value, "tags") else {}
