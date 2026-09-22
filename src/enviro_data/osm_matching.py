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

WATER_CLASSES = frozenset({"lake", "reservoir", "pond", "basin", "lagoon", "bay", "river", "stream", "canal", "drain", "ditch", "coastline", "wetland", "swimming_pool", "other_water"})
PREFERRED_CLASSES = {
    "lake": frozenset({"lake", "reservoir", "pond", "basin", "other_water"}),
    "stream": frozenset({"river", "stream", "canal", "drain", "ditch"}),
    "transition": frozenset({"river", "stream", "lagoon", "bay", "coastline", "wetland", "other_water"}),
    "marine": frozenset({"bay", "coastline"}),
}
TAG_RANKING = {
    "lake": ("lake", "reservoir", "pond", "basin", "lagoon", "other_water", "river", "stream", "wetland", "bay", "coastline"),
    "stream": ("stream", "river", "canal", "drain", "ditch", "other_water", "wetland", "lake", "reservoir", "lagoon", "bay", "coastline"),
    "marine": ("bay", "lagoon", "coastline", "river", "stream", "wetland", "other_water", "lake", "reservoir", "canal", "drain", "ditch"),
    "transition": ("lagoon", "bay", "river", "stream", "wetland", "coastline", "other_water", "lake", "reservoir", "canal", "drain", "ditch"),
    "unknown": ("other_water", "river", "stream", "lake", "reservoir", "pond", "basin", "lagoon", "bay", "wetland", "coastline", "canal", "drain", "ditch"),
}


@dataclass(frozen=True)
class OSMCandidate:
    """A normalized OSM feature (geometry coordinates are lon/lat)."""

    osm_id: str
    geometry: Mapping[str, Any]
    tags: Mapping[str, Any] = field(default_factory=dict)
    feature_class: str = "other_water"
    source: str = "osm"
    osm_type: str = "way"

    @classmethod
    def from_feature(cls, feature: Mapping[str, Any]) -> "OSMCandidate":
        props = dict(feature.get("properties") or feature.get("tags") or {})
        osm_id = feature.get("osm_id", feature.get("id", props.get("osm_id", "")))
        osm_type = str(feature.get("osm_type", feature.get("type", "way")))
        if str(osm_id).startswith(("node/", "way/", "relation/")):
            osm_type, osm_id = str(osm_id).split("/", 1)
        return cls(str(osm_id), feature.get("geometry") or {}, props, classify_water_feature(props), feature.get("source", "osm"), osm_type)


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
    if natural == "water": return {"lake": "lake", "reservoir": "reservoir", "pond": "pond", "basin": "basin", "lagoon": "lagoon", "river": "river"}.get(water, "other_water")
    if natural == "bay": return "bay"
    if natural in {"wetland", "coastline"}: return natural
    if waterway == "riverbank": return "river"
    if waterway in {"river", "stream", "canal", "drain", "ditch"}: return waterway
    if str(tags.get("landuse", "")).lower() == "reservoir": return "reservoir"
    return "other_water"


def _polygons(geom: Mapping[str, Any]) -> list[list[list[tuple[float, float]]]]:
    c, typ = geom.get("coordinates", []), geom.get("type", "")
    if typ == "Polygon": return [[[tuple(map(float, xy[:2])) for xy in ring] for ring in c]]
    if typ == "MultiPolygon": return [[[tuple(map(float, xy[:2])) for xy in ring] for ring in poly] for poly in c]
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


def _segments(points: Sequence[tuple[float, float]], close: bool = False):
    pairs = list(zip(points, points[1:]))
    if close and len(points) > 2 and points[0] != points[-1]:
        pairs.append((points[-1], points[0]))
    return pairs


def _segment_distance_m(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float], ref_lat: float) -> float:
    px, py = _xy(point, ref_lat); ax, ay = _xy(a, ref_lat); bx, by = _xy(b, ref_lat)
    dx, dy = bx - ax, by - ay; t = max(0.0, min(1.0, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy))) if dx or dy else 0.0
    return math.hypot(px - (ax + t*dx), py - (ay + t*dy))


def _feature_distance(point: tuple[float, float], candidate: OSMCandidate) -> tuple[bool, float | None]:
    lat = point[1]
    polygons = _polygons(candidate.geometry)
    if polygons:
        inside = any(
            polygon
            and _point_in_ring(point, polygon[0])
            and not any(_point_in_ring(point, hole) for hole in polygon[1:])
            for polygon in polygons
        )
        dist = min(
            (_segment_distance_m(point, a, b, lat) for polygon in polygons for ring in polygon for a, b in _segments(ring, close=True)),
            default=0.0,
        )
        return inside, 0.0 if inside else dist
    lines = _lines(candidate.geometry)
    if lines:
        return False, min((_segment_distance_m(point, a, b, lat) for line in lines for a, b in _segments(line)), default=None)
    return False, None


def build_overpass_query(lat: float, lon: float, radius_m: float, coast_radius_m: float | None = None) -> str:
    """Build a bounded query for nearby and enclosing water geometries.

    ``is_in`` plus ``pivot`` recovers a large enclosing lake even when its
    shoreline nodes are farther away than ``radius_m``.
    """
    coast_radius = max(radius_m, coast_radius_m or radius_m)
    return (
        "[out:json][timeout:25];"
        f"is_in({lat},{lon})->.areas;"
        "(way(pivot.areas)[natural=water];rel(pivot.areas)[natural=water];"
        "way(pivot.areas)[landuse=reservoir];rel(pivot.areas)[landuse=reservoir];"
        f"way(around:{radius_m},{lat},{lon})[natural=water];"
        f"rel(around:{radius_m},{lat},{lon})[natural=water];"
        f"way(around:{radius_m},{lat},{lon})[waterway];"
        f"rel(around:{radius_m},{lat},{lon})[waterway];"
        f"way(around:{radius_m},{lat},{lon})[landuse=reservoir];"
        f"rel(around:{radius_m},{lat},{lon})[landuse=reservoir];"
        f"way(around:{coast_radius},{lat},{lon})[natural=bay];"
        f"rel(around:{coast_radius},{lat},{lon})[natural=bay];"
        f"way(around:{coast_radius},{lat},{lon})[natural=coastline];"
        ");out geom tags;"
    )


def build_habitat_overpass_query(lat: float, lon: float, radius_m: float, waterbody_type: str) -> str:
    """Build a lightweight ID/tag discovery query for nearby water features."""
    kind = str(waterbody_type or "unknown").lower()
    nearby: list[str] = []
    containing: list[str] = []

    if kind == "lake":
        containing = [
            "way(pivot.areas)[natural=water]",
            "rel(pivot.areas)[natural=water]",
            "way(pivot.areas)[landuse=reservoir]",
            "rel(pivot.areas)[landuse=reservoir]",
        ]
        nearby = ["way[NATURAL]", "rel[NATURAL]", "way[RESERVOIR]", "rel[RESERVOIR]"]
    elif kind == "stream":
        nearby = ["way[WATERWAY]", "rel[WATERWAY]", "way[NATURAL]", "rel[NATURAL]"]
    elif kind == "marine":
        # Marine sample coordinates can sit in estuaries or lagoons inland of
        # the mapped open coast, so retain transitional feature families.
        nearby = ["way[WATERWAY]", "rel[WATERWAY]", "way[NATURAL]", "rel[NATURAL]", "way[WETLAND]", "rel[WETLAND]", "way[COAST]", "way[BAY]", "rel[BAY]"]
    elif kind == "transition":
        nearby = ["way[WATERWAY]", "rel[WATERWAY]", "way[NATURAL]", "rel[NATURAL]", "way[WETLAND]", "rel[WETLAND]", "way[COAST]", "way[BAY]", "rel[BAY]"]
    else:
        nearby = ["way[WATERWAY]", "rel[WATERWAY]", "way[NATURAL]", "rel[NATURAL]", "way[WETLAND]", "rel[WETLAND]", "way[COAST]", "way[BAY]", "rel[BAY]"]

    replacements = {
        "[NATURAL]": f"(around:{radius_m},{lat},{lon})[natural=water]",
        "[RESERVOIR]": f"(around:{radius_m},{lat},{lon})[landuse=reservoir]",
        "[WATERWAY]": f"(around:{radius_m},{lat},{lon})[waterway]",
        "[WETLAND]": f"(around:{radius_m},{lat},{lon})[natural=wetland]",
        "[COAST]": f"(around:{radius_m},{lat},{lon})[natural=coastline]",
        "[BAY]": f"(around:{radius_m},{lat},{lon})[natural=bay]",
    }
    nearby = [next((clause.replace(token, value) for token, value in replacements.items() if token in clause), clause) for clause in nearby]
    prefix = f"is_in({lat},{lon})->.areas;" if containing else ""
    return "[out:json][timeout:25];" + prefix + "(" + ";".join(containing + nearby) + ";);out tags;"


def rank_tag_candidates(elements: Iterable[Mapping[str, Any]], expected_waterbody_type: str | None = None) -> list[OSMCandidate]:
    """Rank ID/tag-only Overpass results deterministically for a habitat."""
    kind = str(expected_waterbody_type or "unknown").lower()
    order = TAG_RANKING.get(kind, TAG_RANKING["unknown"])
    priority = {feature_class: index for index, feature_class in enumerate(order)}
    candidates: dict[tuple[str, str], OSMCandidate] = {}
    for element in elements:
        osm_type = str(element.get("type", "way"))
        osm_id = str(element.get("id", ""))
        if osm_type not in {"way", "relation"} or not osm_id:
            continue
        tags = dict(element.get("tags") or {})
        candidate = OSMCandidate(osm_id, {}, tags, classify_water_feature(tags), "osm", osm_type)
        candidates[(osm_type, osm_id)] = candidate
    type_priority = {"relation": 0, "way": 1}
    return sorted(
        candidates.values(),
        key=lambda candidate: (
            priority.get(candidate.feature_class, len(priority)),
            0 if candidate.tags.get("name") else 1,
            type_priority.get(candidate.osm_type, 2),
            (0, int(candidate.osm_id)) if candidate.osm_id.isdigit() else (1, candidate.osm_id),
        ),
    )


def match_ranked_tags(sample_id: str, candidates: Sequence[OSMCandidate], expected_waterbody_type: str | None = None, search_radius_m: float | None = None) -> OSMMatch:
    """Select the best tag-ranked feature without claiming geometric distance."""
    if not candidates:
        return OSMMatch(sample_id, None, match_method="unmatched", diagnostics={"candidate_count": 0, "search_radius_m": search_radius_m})
    best = candidates[0]
    same_class = [candidate for candidate in candidates if candidate.feature_class == best.feature_class]
    alternatives = [
        {"osm_type": candidate.osm_type, "osm_id": candidate.osm_id, "feature_class": candidate.feature_class}
        for candidate in candidates[:5]
    ]
    preferred = PREFERRED_CLASSES.get(str(expected_waterbody_type or "").lower(), frozenset())
    conflict = bool(preferred and best.feature_class not in preferred)
    return OSMMatch(
        sample_id,
        best.osm_id,
        best.tags,
        best.feature_class,
        "ranked_tags_within_radius",
        None,
        len(same_class) > 1 or conflict,
        {
            "candidate_count": len(candidates),
            "expected_waterbody_type": expected_waterbody_type,
            "expected_class_conflict": conflict,
            "same_class_candidate_count": len(same_class),
            "search_radius_m": search_radius_m,
            "top_candidates": alternatives,
        },
    )


def build_ranked_geometry_query(osm_type: str, osm_id: str, lat: float, lon: float, radius_m: float) -> str:
    """Fetch one ranked feature with geometry clipped to the local window."""
    if osm_type not in {"way", "relation"}:
        raise ValueError(f"unsupported OSM type for geometry retrieval: {osm_type}")
    radius = max(float(radius_m), 1.0)
    lat_delta = radius / 111_320.0
    lon_scale = max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius / (111_320.0 * lon_scale)
    south, west = lat - lat_delta, lon - lon_delta
    north, east = lat + lat_delta, lon + lon_delta
    return f"[out:json][timeout:25];{osm_type}(id:{osm_id});out geom({south:.7f},{west:.7f},{north:.7f},{east:.7f}) tags;"


class OverpassClient:
    """Optional Overpass retrieval with deterministic JSON file caching."""
    def __init__(self, cache_dir: str | Path | None = None, endpoint: str = "https://overpass-api.de/api/interpreter", ttl_seconds: int = 30 * 86400, http_get: Callable[..., Any] | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else None; self.endpoint = endpoint; self.ttl_seconds = ttl_seconds; self.http_get = http_get

    def fetch(self, lat: float, lon: float, radius_m: float) -> list[OSMCandidate]:
        query = build_overpass_query(lat, lon, radius_m)
        key = hashlib.sha256(query.encode()).hexdigest(); path = self.cache_dir / f"overpass_{key}.json" if self.cache_dir else None
        payload = None
        if path and path.exists() and time.time() - path.stat().st_mtime <= self.ttl_seconds: payload = json.loads(path.read_text(encoding="utf-8"))
        if payload is None:
            if self.http_get is None:
                import requests
                self.http_get = requests.get
            response = self.http_get(
                self.endpoint,
                data={"data": query},
                headers={"User-Agent": "stickleback-environmental-metrics/0.1"},
                timeout=45,
            ); response.raise_for_status(); payload = response.json()
            if path: path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload), encoding="utf-8")
        return [OSMCandidate.from_feature(overpass_element_to_feature(x)) for x in payload.get("elements", [])]


def _stitch_rings(parts: Sequence[Sequence[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Join relation-member way geometries into closed rings."""
    remaining = [list(part) for part in parts if len(part) >= 2]
    rings: list[list[tuple[float, float]]] = []
    while remaining:
        ring = remaining.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for index, part in enumerate(remaining):
                if ring[-1] == part[0]:
                    ring.extend(part[1:])
                elif ring[-1] == part[-1]:
                    ring.extend(reversed(part[:-1]))
                elif ring[0] == part[-1]:
                    ring = part[:-1] + ring
                elif ring[0] == part[0]:
                    ring = list(reversed(part[1:])) + ring
                else:
                    continue
                remaining.pop(index)
                changed = True
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append(ring)
    return rings


def overpass_element_to_feature(element: Mapping[str, Any]) -> dict[str, Any]:
    """Convert Overpass ``out geom`` ways or multipolygon relations to GeoJSON."""
    osm_type = str(element.get("type", "way"))
    if osm_type == "relation":
        members = element.get("members") or []
        groups: dict[str, list[list[tuple[float, float]]]] = {"outer": [], "inner": []}
        for member in members:
            role = str(member.get("role") or "outer")
            if role not in groups or not member.get("geometry"):
                continue
            groups[role].append([(float(p["lon"]), float(p["lat"])) for p in member["geometry"]])
        outers, inners = _stitch_rings(groups["outer"]), _stitch_rings(groups["inner"])
        polygons: list[list[list[tuple[float, float]]]] = [[outer] for outer in outers]
        for inner in inners:
            target = next((polygon for polygon in polygons if _point_in_ring(inner[0], polygon[0])), None)
            if target is not None:
                target.append(inner)
        geometry: Mapping[str, Any]
        if len(polygons) == 1:
            geometry = {"type": "Polygon", "coordinates": polygons[0]}
        else:
            geometry = {"type": "MultiPolygon", "coordinates": polygons}
    else:
        raw = element.get("geometry") or []
        coords = [(float(p["lon"]), float(p["lat"])) for p in raw]
        typ = "Polygon" if len(coords) >= 4 and coords[0] == coords[-1] else "LineString"
        geometry = {"type": typ, "coordinates": [coords] if typ == "Polygon" else coords}
    return {
        "id": f"{osm_type}/{element.get('id', '')}",
        "osm_type": osm_type,
        "geometry": geometry,
        "tags": element.get("tags", {}),
    }


class OSMMatcher:
    def __init__(self, candidates: Iterable[OSMCandidate | Mapping[str, Any]] | None = None, retriever: OverpassClient | Callable[..., Iterable[Any]] | None = None, search_radius_m: float = 1000.0, intersect_tolerance_m: float = 1.0, ambiguity_tolerance_m: float = 5.0):
        self.candidates = [c if isinstance(c, OSMCandidate) else OSMCandidate.from_feature(c) for c in (candidates or [])]; self.retriever = retriever; self.search_radius_m = search_radius_m; self.intersect_tolerance_m = intersect_tolerance_m; self.ambiguity_tolerance_m = ambiguity_tolerance_m

    def match(self, sample_id: str, lat: float, lon: float, expected_waterbody_type: str | None = None) -> OSMMatch:
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
        preferred = PREFERRED_CLASSES.get(str(expected_waterbody_type or "").lower(), frozenset())
        eligible.sort(key=lambda x: (0 if not preferred or x[0].feature_class in preferred else 1, x[2] if x[2] is not None else float("inf"), x[0].osm_type, x[0].osm_id))
        best = eligible[0]
        tied = [x for x in eligible if x[2] is not None and abs(x[2] - best[2]) <= self.ambiguity_tolerance_m]
        alternatives = [
            {"osm_type": x[0].osm_type, "osm_id": x[0].osm_id, "feature_class": x[0].feature_class, "distance_m": round(x[2], 3)}
            for x in eligible[:5] if x[2] is not None
        ]
        conflict = bool(preferred and best[0].feature_class not in preferred)
        return OSMMatch(sample_id, best[0].osm_id, best[0].tags, best[0].feature_class, method, round(best[2], 3) if best[2] is not None else None, len(tied) > 1 or conflict, {"candidate_count": len(scored), "expected_waterbody_type": expected_waterbody_type, "expected_class_conflict": conflict, "tied_osm_ids": [x[0].osm_id for x in tied] if len(tied) > 1 else [], "top_candidates": alternatives})

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
        return self.match(sample_id, float(lat), float(lon), point.get("working_waterbody_type"))


def match_water_feature(sample_id: str, lat: float, lon: float, candidates: Iterable[OSMCandidate | Mapping[str, Any]] | None = None, **kwargs: Any) -> OSMMatch:
    return OSMMatcher(candidates, **kwargs).match(sample_id, lat, lon)
