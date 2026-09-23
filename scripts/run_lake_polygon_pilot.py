"""Reproducible 40-lake OSM pilot with full geometry and conservative status.

Offline by default. A live run stops after repeated Overpass errors and retains
its partial results for inspection. Never uses a clipped polygon for metrics.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from enviro_data.lake_polygons import complete_polygon, contains, full_geometry_query, name_agreement, polygon_metrics
from enviro_data.osm_matching import rank_tag_candidates
from enviro_data.site_habitat import infer_site_habitat, normalize_site_name

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "site_overview_v1_clean.csv"
ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "stickleback-environmental-metrics/0.1 (lake polygon pilot)"
LOGGER = logging.getLogger(__name__)


def nearby_lake_query(lat: float, lon: float, radius: int) -> str:
    """Fallback for samples near shore or missing derived Overpass areas."""
    clauses = ";".join(f'{kind}(around:{radius},{lat},{lon})[{tag}]'
                       for kind in ("way", "rel") for tag in ("natural=water", "landuse=reservoir"))
    return f"[out:json][timeout:25];({clauses};);out tags;"


def containing_lake_query(lat: float, lon: float) -> str:
    """Find OSM water areas enclosing the point, independent of shore distance.

    Overpass is_in yields closed ways and derived relation areas; pivot returns
    the source ways/relations. Complete geometry is fetched only after ranking.
    """
    return (f"[out:json][timeout:25];is_in({lat},{lon})->.areas;"
            "(way(pivot.areas)[natural=water];rel(pivot.areas)[natural=water];"
            "way(pivot.areas)[landuse=reservoir];rel(pivot.areas)[landuse=reservoir];);out tags;")


def select_lakes(source: Path, count: int = 40):
    with source.open(encoding="utf-8-sig", newline="") as file:
        records = list(csv.DictReader(file))
    eligible = []
    used_names = set()
    for row in records:
        inference = infer_site_habitat(row["Population.name"], row["Ecotype"])
        name = normalize_site_name(row["Population.name"])
        if (inference.working_waterbody_type != "lake" or row["Ecotype"].strip().lower() != "freshwater"
                or inference.name_inference_confidence != "high" or not name or name in used_names):
            continue
        eligible.append(row)
        used_names.add(name)
    if len(eligible) < count:
        raise ValueError(f"only {len(eligible)} eligible named lake sites for {count} requested")
    # Evenly sample the latitude-sorted candidates for geographic breadth.
    eligible.sort(key=lambda r: (float(r["Latitude"]), r["sample_id"]))
    return [eligible[(i * len(eligible) + len(eligible) // 2) // count] for i in range(count)]


class OverpassUnavailable(Exception):
    pass


class CacheClient:
    def __init__(self, cache_dir: Path, live: bool = False, delay: float = 2, timeout: float = 10):
        self.cache_dir, self.live, self.delay, self.timeout = cache_dir, live, delay, timeout
        self.last_request = None

    def fetch(self, query):
        key = hashlib.sha256(query.encode()).hexdigest()[:24]
        cache = self.cache_dir / f"{key}.json"
        if cache.exists():
            return json.loads(cache.read_text(encoding="utf-8")), "cache", cache
        if not self.live:
            raise OverpassUnavailable("cache_miss_live_disabled")
        if self.last_request is not None:
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        request = Request(ENDPOINT, data=urlencode({"data": query}).encode(), headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read(8_000_001)
                if len(data) > 8_000_000:
                    raise OverpassUnavailable("response_exceeds_8MB")
            payload = json.loads(data)
            if "elements" not in payload:
                raise OverpassUnavailable("no_elements_in_response")
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise OverpassUnavailable(f"{type(error).__name__}: {error}") from error
        finally:
            self.last_request = time.monotonic()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload, "network", cache


def evaluate_lake(row, client):
    lat, lon = float(row["Latitude"]), float(row["Longitude"])
    result = {"sample_id": row["sample_id"], "population_name": row["Population.name"],
              "latitude": lat, "longitude": lon, "osm_type": "", "osm_id": "", "osm_name": "",
              "search_radius_m": "", "discovery_stage": "", "candidate_count": 0, "point_inside_polygon": "",
              "name_evidence": "", "lake_area_m2": "", "lake_perimeter_m": "",
              "lake_area_perimeter_m": "", "lake_shoreline_development": "",
              "status": "no_polygon", "review_required": True, "diagnostics": "", "retrieval_source": "",
              "query_date_utc": datetime.now(timezone.utc).isoformat(), "geometry_cache": ""}
    candidates = {}
    failed_shapes = []
    searches = [(0, "containing_area", containing_lake_query(lat, lon)),
                (100, "nearby_100m", nearby_lake_query(lat, lon, 100)),
                (500, "nearby_500m", nearby_lake_query(lat, lon, 500))]
    for radius, stage, query in searches:
        payload, source, _ = client.fetch(query)
        result["retrieval_source"] = source
        result["search_radius_m"] = radius
        result["discovery_stage"] = stage
        for element in payload.get("elements", []):
            candidates[(str(element.get("type")), str(element.get("id")))] = element
        ranked = [c for c in rank_tag_candidates(candidates.values(), "lake") if c.feature_class in {"lake", "reservoir", "pond", "basin", "other_water"}]
        result["candidate_count"] = len(ranked)
        # Query nearby geometry for up to three candidates. Require containment
        # before accepting a lake area, even when the point is near a shore.
        matches = []
        for candidate in ranked[:3]:
            try:
                whole, shape_source, cache = client.fetch(full_geometry_query(candidate.osm_type, candidate.osm_id))
                obj = next((e for e in whole.get("elements", []) if str(e.get("id")) == candidate.osm_id and e.get("type") == candidate.osm_type), None)
                if obj is None:
                    raise ValueError("selected_object_missing")
                polygons = complete_polygon(obj)
                if not contains(polygons, lon, lat):
                    failed_shapes.append(f"{candidate.osm_type}/{candidate.osm_id}:point_outside_polygon")
                    continue
                evidence = name_agreement(row["Population.name"], obj.get("tags") or {})
                matches.append((evidence != "name_agrees", candidate, obj, polygons, shape_source, cache, evidence))
            except ValueError as error:
                failed_shapes.append(f"{candidate.osm_type}/{candidate.osm_id}:{error}")
        if matches:
            matches.sort(key=lambda entry: entry[0])
            _, candidate, obj, polygons, shape_source, cache, evidence = matches[0]
            metrics = polygon_metrics(polygons)
            result.update(metrics)
            result.update(osm_type=candidate.osm_type, osm_id=candidate.osm_id,
                          osm_name=(obj.get("tags") or {}).get("name", ""),
                          point_inside_polygon=True, name_evidence=evidence,
                          status="candidate_polygon", review_required=True,
                          retrieval_source=shape_source, geometry_cache=str(cache))
            result["diagnostics"] = json.dumps({"other_containing_candidates": len(matches) - 1, "rejected": failed_shapes})
            geometry = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
            return result, {"type": "Feature", "id": f"{candidate.osm_type}/{candidate.osm_id}", "properties": {"sample_id": row["sample_id"], "name_evidence": evidence, **metrics}, "geometry": geometry}
    result["diagnostics"] = json.dumps({"rejected": failed_shapes})
    return result, None


def run(source=DEFAULT_INPUT, output_dir=ROOT / "data/lake_pilot", *, live=False, count=40, delay=2., timeout=10., max_failures=2):
    rows = select_lakes(source, count)
    client = CacheClient(output_dir / "raw_responses", live, delay, timeout)
    results, features = [], []
    failures = 0
    for index, row in enumerate(rows, 1):
        LOGGER.info("lake=%s progress=%d/%d", row["sample_id"], index, len(rows))
        try:
            result, feature = evaluate_lake(row, client)
            failures = 0
        except OverpassUnavailable as error:
            result = {"sample_id": row["sample_id"], "population_name": row["Population.name"],
                      "latitude": row["Latitude"], "longitude": row["Longitude"],
                      "status": "retrieval_failed" if live else "cache_missing", "review_required": True,
                      "diagnostics": str(error)}
            feature = None
            if live:
                failures += 1
                LOGGER.warning("lake=%s %s; consecutive_failures=%d", row["sample_id"], error, failures)
        results.append(result)
        if feature:
            features.append(feature)
        if live and failures >= max_failures:
            LOGGER.error("stopped after %d consecutive failed sites", failures)
            break
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = ["sample_id", "population_name", "latitude", "longitude", "osm_type", "osm_id", "osm_name", "search_radius_m", "discovery_stage", "candidate_count", "point_inside_polygon", "name_evidence", "lake_area_m2", "lake_perimeter_m", "lake_area_perimeter_m", "lake_shoreline_development", "status", "review_required", "diagnostics", "retrieval_source", "query_date_utc", "geometry_cache"]
    dest = output_dir / "lake_polygon_pilot.csv"
    with dest.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore"); writer.writeheader(); writer.writerows(results)
    (output_dir / "lake_polygon_pilot.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    (output_dir / "run_metadata.json").write_text(json.dumps({"source": str(source), "selected_ids": [r["sample_id"] for r in rows], "processed": len(results), "polygon_candidates": len(features), "live": live, "request_delay_seconds": delay, "timeout_seconds": timeout, "stopped_for_errors": live and failures >= max_failures, "area_method": "spherical WGS84 approximation, full OSM object, islands subtracted", "perimeter_method": "great-circle ring segments, including islands", "depth_equation": "pending_user_thesis"}, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/lake_pilot")
    parser.add_argument("--live-osm", action="store_true")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--request-delay-seconds", type=float, default=2.)
    parser.add_argument("--timeout-seconds", type=float, default=10.)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rows = run(args.input, args.output_dir, live=args.live_osm, count=args.count,
               delay=args.request_delay_seconds, timeout=args.timeout_seconds)
    print(json.dumps({"processed": len(rows), "status_counts": {status: sum(r["status"] == status for r in rows)
                      for status in ("candidate_polygon", "no_polygon", "cache_missing", "retrieval_failed")}}))
