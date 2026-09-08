"""Offline-friendly matching of WGS84 sample points to OSM water features.

The matcher consumes GeoJSON-like feature dictionaries, making retrieval easy to
mock in tests. :class:`OverpassClient` is an optional, file-cached network
adapter; no network request is made by the matcher itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

WATER_CLASSES = frozenset({"lake", "reservoir", "pond", "river", "stream", "canal", "drain", "ditch", "coastline", "wetland", "swimming_pool", "other_water"})


@dataclass(frozen=True)
class OSMCandidate:
    """A normalized OSM feature (geometry coordinates are lon/lat)."""

    osm_id: str
    geometry: Mapping[str, Any]
    tags: Mapping[str, Any] = field(default_factory=dict)
    feature_class: str = "other_water"
    source: str = "osm"

    @classmethod
    def from_feature(cls, feature: Mapping[str, Any]) -> "OSMCandidate":
        props = dict(feature.get("properties") or feature.get("tags") or {})
        osm_id = feature.get("osm_id", feature.get("id", props.get("osm_id", "")))
        if str(osm_id).startswith(("node/", "way/", "relation/")):
            osm_id = str(osm_id).split("/", 1)[1]
        return cls(str(osm_id), feature.get("geometry") or {}, props, classify_water_feature(props), feature.get("source", "osm"))


@dataclass(frozen=True)
class OSMMatch:
    sample_id: str
    osm_id: str | None
    tags: Mapping[str, Any] = field(default_factory=dict)
    feature_class: str | None = None
    match_method: str = "unmatched"
    distance_m: float | None = None
    review_required: bool = False
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"sample_id": self.sample_id, "osm_id": self.osm_id, "osm_tags": dict(self.tags), "water_feature_class": self.feature_class, "match_method": self.match_method, "distance_m": self.distance_m, "manual_review": self.review_required, "match_diagnostics": dict(self.diagnostics)}


def classify_water_feature(tags: Mapping[str, Any]) -> str:
    """Map OSM tags to a stable, controlled water-feature class."""
    natural = str(tags.get("natural", "")).lower()
    water = str(tags.get("water", "")).lower()
    waterway = str(tags.get("waterway", "")).lower()
    leisure = str(tags.get("leisure", "")).lower()
    if leisure == "swimming_pool": return "swimming_pool"
    if natural == "water": return {"lake": "lake", "reservoir": "reservoir", "pond": "pond", "river": "river"}.get(water, "other_water")
    if natural in {"wetland", "coastline"}: return natural
    if waterway in {"river", "stream", "canal", "drain", "ditch"}: return waterway
    if str(tags.get("landuse", "")).lower() == "reservoir": return "reservoir"
    return "other_water"


def _rings(geom: Mapping[str, Any]) -> list[list[tuple[float, float]]]:
    c, typ = geom.get("coordinates", []), geom.get("type", "")
    if typ == "Polygon": return [[(float(x), float(y)) for x, y, *_ in ring] for ring in c]
    if typ == "MultiPolygon": return [[(float(x), float(y)) for x, y, *_ in ring] for poly in c for ring in poly]
    return []


def _lines(geom: Mapping[str, Any]) -> list[list[tuple[float, float]]]:
    c, typ = geom.get("coordinates", []), geom.get("type", "")
    if typ == "LineString": return [[(float(x), float(y)) for x, y, *_ in c]]
    if typ == "MultiLineString": return [[(float(x), float(y)) for x, y, *_ in line] for line in c]
    return []


def _xy(point: tuple[float, float], ref_lat: float) -> tuple[float, float]:
    lon, lat = point; k = 111320.0; return (lon * k * math.cos(math.radians(ref_lat)), lat * k)


def _point_in_ring(point: tuple[float, float], ring: Sequence[tuple[float, float]]) -> bool:
    x, y = point; inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if ((y1 > y) != (y2 > y)) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: inside = not inside
    return inside


def _segment_distance_m(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float], ref_lat: float) -> float:
    px, py = _xy(point, ref_lat); ax, ay = _xy(a, ref_lat); bx, by = _xy(b, ref_lat)
    dx, dy = bx - ax, by - ay; t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy))) if dx or dy else 0.0
    return math.hypot(px - (ax + t*dx), py - (ay + t*dy))


def _feature_distance(point: tuple[float, float], candidate: OSMCandidate) -> tuple[bool, float | None]:
    typ = candidate.geometry.get("type", ""); lat = point[1]
    rings = _rings(candidate.geometry)
    if rings:
        inside = _point_in_ring(point, rings[0]) and not any(_point_in_ring(point, r) for r in rings[1:])
        dist = min((_segment_distance_m(point, a, b, lat) for r in rings for a, b in zip(r, r[1:])), default=0.0)
        return inside, 0.0 if inside else dist
    lines = _lines(candidate.geometry)
    if lines:
        return False, min((_segment_distance_m(point, a, b, lat) for line in lines for a, b in zip(line, line[1:])), default=None)
    return False, None


class OverpassClient:
    """Optional Overpass retrieval with deterministic JSON file caching."""
    def __init__(self, cache_dir: str | Path | None = None, endpoint: str = "https://overpass-api.de/api/interpreter", ttl_seconds: int = 30 * 86400, http_get: Callable[..., Any] | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else None; self.endpoint = endpoint; self.ttl_seconds = ttl_seconds; self.http_get = http_get

    def fetch(self, lat: float, lon: float, radius_m: float) -> list[OSMCandidate]:
        key = hashlib.sha256(f"{lat:.6f},{lon:.6f},{radius_m:.1f}".encode()).hexdigest(); path = self.cache_dir / f"overpass_{key}.json" if self.cache_dir else None
        payload = None
        if path and path.exists() and time.time() - path.stat().st_mtime <= self.ttl_seconds: payload = json.loads(path.read_text(encoding="utf-8"))
        if payload is None:
            if self.http_get is None:
                import requests
                self.http_get = requests.get
            q = f"[out:json];(way(around:{radius_m},{lat},{lon})[natural=water];way(around:{radius_m},{lat},{lon})[waterway];way(around:{radius_m},{lat},{lon})[landuse=reservoir];);out geom tags;"
            response = self.http_get(self.endpoint, params={"data": q}, timeout=30); response.raise_for_status(); payload = response.json()
            if path: path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload), encoding="utf-8")
        return [OSMCandidate.from_feature(_overpass_to_feature(x)) for x in payload.get("elements", [])]


def _overpass_to_feature(element: Mapping[str, Any]) -> dict[str, Any]:
    geom = element.get("geometry", []); coords = [(p["lon"], p["lat"]) for p in geom]
    typ = "Polygon" if len(coords) >= 3 and coords[0] == coords[-1] else "LineString"
    return {"id": f"way/{element.get('id', '')}", "geometry": {"type": typ, "coordinates": [coords] if typ == "Polygon" else coords}, "tags": element.get("tags", {})}


class OSMMatcher:
    def __init__(self, candidates: Iterable[OSMCandidate | Mapping[str, Any]] | None = None, retriever: OverpassClient | Callable[..., Iterable[Any]] | None = None, search_radius_m: float = 1000.0, intersect_tolerance_m: float = 1.0, ambiguity_tolerance_m: float = 5.0):
        self.candidates = [c if isinstance(c, OSMCandidate) else OSMCandidate.from_feature(c) for c in (candidates or [])]; self.retriever = retriever; self.search_radius_m = search_radius_m; self.intersect_tolerance_m = intersect_tolerance_m; self.ambiguity_tolerance_m = ambiguity_tolerance_m

    def match(self, sample_id: str, lat: float, lon: float) -> OSMMatch:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("latitude/longitude must be WGS84 degrees")
        candidates = list(self.candidates)
        if not candidates and self.retriever:
            fetched = self.retriever.fetch(lat, lon, self.search_radius_m) if hasattr(self.retriever, "fetch") else self.retriever(lat, lon, self.search_radius_m)
            candidates = [x if isinstance(x, OSMCandidate) else OSMCandidate.from_feature(x) for x in fetched]
        scored = [(c, *_feature_distance((lon, lat), c)) for c in candidates if c.feature_class in WATER_CLASSES]
        containing = [x for x in scored if x[1] and x[2] is not None]
        method = "contains_water_polygon" if containing else None
        eligible = containing or [x for x in scored if x[2] is not None and x[2] <= self.search_radius_m]
        if not eligible: return OSMMatch(sample_id, None, match_method="unmatched", diagnostics={"candidate_count": len(scored), "search_radius_m": self.search_radius_m})
        if method is None:
            intersections = [x for x in eligible if x[0].geometry.get("type", "").endswith("LineString") and x[2] <= self.intersect_tolerance_m]
            if intersections:
                method, eligible = "intersects_waterway", intersections
            else:
                method = "nearest_feature"
        eligible.sort(key=lambda x: (x[2] if x[2] is not None else float("inf"), x[0].osm_id)); best = eligible[0]; tied = [x for x in eligible if x[2] is not None and abs(x[2] - best[2]) <= self.ambiguity_tolerance_m]
        return OSMMatch(sample_id, best[0].osm_id, best[0].tags, best[0].feature_class, method, round(best[2], 3) if best[2] is not None else None, len(tied) > 1, {"candidate_count": len(scored), "tied_osm_ids": [x[0].osm_id for x in tied] if len(tied) > 1 else []})

    def match_point(self, point: Mapping[str, Any]) -> OSMMatch:
        """Match a record containing ``sample_id`` and WGS84 coordinates.

        Accepted coordinate keys are ``latitude``/``longitude`` or ``lat``/``lon``;
        a GeoJSON Point geometry may also be supplied under ``geometry``.
        """
        sample_id = str(point.get("sample_id", ""))
        geometry = point.get("geometry")
        if geometry and geometry.get("type") == "Point":
            lon, lat = geometry["coordinates"][:2]
        else:
            lat = point.get("latitude", point.get("lat")); lon = point.get("longitude", point.get("lon"))
        if lat is None or lon is None: raise ValueError("point requires latitude/longitude or a GeoJSON Point geometry")
        return self.match(sample_id, float(lat), float(lon))


def match_water_feature(sample_id: str, lat: float, lon: float, candidates: Iterable[OSMCandidate | Mapping[str, Any]] | None = None, **kwargs: Any) -> OSMMatch:
    return OSMMatcher(candidates, **kwargs).match(sample_id, lat, lon)
