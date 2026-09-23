"""Conservative whole-lake OSM polygon validation and spherical geometry metrics.

These are candidate lake metrics. A human still needs to verify waterbody identity.
"""
from __future__ import annotations

import math
from typing import Mapping

from .osm_matching import _point_in_ring, _stitch_rings
from .site_habitat import normalize_site_name

EARTH_RADIUS_M = 6_371_008.8


def full_geometry_query(osm_type: str, osm_id: str) -> str:
    """Fetch one whole object; clipped geometry must never produce lake area."""
    if osm_type not in {"way", "relation"} or not str(osm_id).isdigit():
        raise ValueError("OSM lake requires a way or relation with a numeric ID")
    return f"[out:json][timeout:25];{osm_type}(id:{osm_id});out geom tags;"


def _ring(points):
    result = [(float(p["lon"]), float(p["lat"])) for p in points]
    if len(result) < 4 or result[0] != result[-1] or len(set(result[:-1])) < 3:
        raise ValueError("open_or_degenerate_ring")
    if any(not math.isfinite(x) or not math.isfinite(y) or abs(y) > 90 or abs(x) > 180 for x, y in result):
        raise ValueError("invalid_coordinate")
    return result


def complete_polygon(element: Mapping, max_vertices: int = 150_000):
    """Reject missing relation members, unclosed rings, and orphan island holes."""
    if element.get("type") == "way":
        polygons = [[_ring(element.get("geometry") or [])]]
    elif element.get("type") == "relation":
        members = element.get("members") or []
        parts = {"outer": [], "inner": []}
        for member in members:
            role = member.get("role") or "outer"
            if role not in parts:
                raise ValueError("unknown_relation_role")
            if not member.get("geometry"):
                raise ValueError("missing_relation_member_geometry")
            parts[role].append([(float(p["lon"]), float(p["lat"])) for p in member["geometry"]])
        if not parts["outer"]:
            raise ValueError("missing_outer_ring")
        outer = _stitch_rings(parts["outer"])
        inner = _stitch_rings(parts["inner"])
        if sum(len(r) - 1 for r in outer) != sum(len(p) - 1 for p in parts["outer"]) or sum(len(r) - 1 for r in inner) != sum(len(p) - 1 for p in parts["inner"]):
            raise ValueError("unclosed_relation_members")
        polygons = [[_ring([{"lon": x, "lat": y} for x, y in ring])] for ring in outer]
        for ring in inner:
            hole = _ring([{"lon": x, "lat": y} for x, y in ring])
            parents = [poly for poly in polygons if _point_in_ring(hole[0], poly[0])]
            if len(parents) != 1:
                raise ValueError("orphan_or_ambiguous_inner_ring")
            parents[0].append(hole)
    else:
        raise ValueError("unsupported_osm_object")
    if sum(len(r) for p in polygons for r in p) > max_vertices:
        raise ValueError("too_many_vertices")
    return polygons


def contains(polygons, lon: float, lat: float) -> bool:
    point = (lon, lat)
    return any(_point_in_ring(point, poly[0]) and not any(_point_in_ring(point, hole) for hole in poly[1:]) for poly in polygons)


def _lon_delta(lon1, lon2):
    return (lon2 - lon1 + 180) % 360 - 180


def _area(ring):
    return abs(sum(math.radians(_lon_delta(x1, x2)) * (math.sin(math.radians(y1)) + math.sin(math.radians(y2)))
                   for (x1, y1), (x2, y2) in zip(ring, ring[1:])) * EARTH_RADIUS_M ** 2 / 2)


def _length(ring):
    total = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        dlat, dlon = math.radians(y2 - y1), math.radians(_lon_delta(x1, x2))
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(y1)) * math.cos(math.radians(y2)) * math.sin(dlon / 2) ** 2
        total += 2 * EARTH_RADIUS_M * math.asin(min(1, math.sqrt(a)))
    return total


def polygon_metrics(polygons):
    area = sum(_area(poly[0]) - sum(_area(hole) for hole in poly[1:]) for poly in polygons)
    # Include island boundaries in shoreline length; report this definition.
    perimeter = sum(_length(ring) for poly in polygons for ring in poly)
    if area <= 0 or perimeter <= 0:
        raise ValueError("invalid_polygon_area_or_perimeter")
    return {
        "lake_area_m2": round(area, 2),
        "lake_perimeter_m": round(perimeter, 2),
        "lake_area_perimeter_m": round(area / perimeter, 3),
        "lake_shoreline_development": round(perimeter / (2 * math.sqrt(math.pi * area)), 5),
    }


def name_agreement(site_name: str, tags: Mapping) -> str:
    """Return evidence, never certify translations or unnamed lakes as matches."""
    names = [tags.get(k, "") for k in ("name", "name:en", "alt_name", "official_name")]
    site = set(normalize_site_name(site_name).split()) - {"lake", "pond", "reservoir", "loch", "lough"}
    if any(site and site <= set(normalize_site_name(name).split()) for name in names if name):
        return "name_agrees"
    return "name_differs" if any(names) else "osm_unnamed"
