"""Bounded, resumable Overpass discovery and core OSM geometry retrieval."""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from .lake_polygons import complete_polygon, contains, full_geometry_query, name_agreement, osm_api_geometry, polygon_metrics
from .osm_matching import classify_water_feature, rank_tag_candidates
from .osm_http import bounded_urlopen as urlopen

LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://overpass-api.de/api/interpreter"
CORE_API = "https://api.openstreetmap.org/api/0.6"
ALLOWED = {"lake", "reservoir", "pond", "basin", "other_water"}
PIPELINE_VERSION = "hybrid-lake-v1"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def append_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(value, ensure_ascii=False) + "\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def nearby_lake_query(lat, lon, radius):
    clauses = ";".join(f'{kind}(around:{radius},{lat},{lon})[{tag}]'
                       for kind in ("way", "rel") for tag in ("natural=water", "landuse=reservoir"))
    return f"[out:json][timeout:25];({clauses};);out tags;"


def containing_lake_query(lat, lon):
    return (f"[out:json][timeout:25];is_in({lat},{lon})->.areas;"
            "(way(pivot.areas)[natural=water];rel(pivot.areas)[natural=water];"
            "way(pivot.areas)[landuse=reservoir];rel(pivot.areas)[landuse=reservoir];);out tags;")


class OverpassUnavailable(Exception):
    """Retrieval failed; never interpret this as absence of water."""


class CacheClient:
    def __init__(self, cache_dir, live=False, delay=2, timeout=30, endpoint=ENDPOINT,
                 retries=1, max_requests=320):
        self.cache_dir = Path(cache_dir)
        self.live, self.delay, self.timeout, self.endpoint = live, delay, timeout, endpoint
        self.retries, self.max_requests = retries, max_requests
        self.last_request = None
        self.cooldown_until = 0
        self.request_count = 0
        if delay < 0 or timeout <= 0 or retries < 0 or max_requests < 1:
            raise ValueError("invalid network limits")

    def cache_path(self, url, data=None):
        identity = url.encode() + b"\n" + (data or b"")
        return self.cache_dir / (hashlib.sha256(identity).hexdigest()[:24] + ".json")

    def _fetch(self, url, data=None, *, stage):
        cache = self.cache_path(url, data)
        if cache.exists():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                self._validate(payload)
            except (ValueError, OverpassUnavailable) as error:
                raise OverpassUnavailable(f"invalid_cache {cache}: {error}") from error
            LOGGER.info("stage=%s cache_hit elements=%d", stage, len(payload["elements"]))
            return payload, "cache", cache
        if not self.live:
            raise OverpassUnavailable(f"stage={stage} cache_miss_live_disabled")
        for attempt in range(self.retries + 1):
            if self.request_count >= self.max_requests:
                raise OverpassUnavailable("request_budget_exhausted")
            if self.last_request is not None:
                time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            remaining = max(0, self.cooldown_until - time.monotonic())
            while remaining > 0:
                interval = min(60, remaining)
                time.sleep(interval)
                remaining -= interval
            self.cooldown_until = 0
            self.request_count += 1
            started = time.monotonic()
            event = {"requested_at_utc": now(), "url": url, "stage": stage, "attempt": attempt + 1,
                     "cache": str(cache), "request_number": self.request_count}
            LOGGER.info("stage=%s request_start attempt=%d request=%d", stage, attempt + 1, self.request_count)
            retryable = True
            retry_wait = 2 * (attempt + 1)
            try:
                with urlopen(Request(url, data=data, headers={"User-Agent": "stickleback-environmental-metrics/0.1 (bounded lake pilot)"}), timeout=self.timeout) as response:
                    raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    retryable = False
                    raise OverpassUnavailable("response_exceeds_8MB")
                payload = json.loads(raw)
                self._validate(payload)
                atomic_json(cache, payload)
                atomic_json(cache.with_suffix(".meta.json"), {**event, "retrieved_at_utc": now(), "bytes": len(raw)})
                event.update(status="ok", bytes=len(raw), elements=len(payload["elements"]))
                return payload, "network", cache
            except (HTTPError, URLError, OSError, ValueError, OverpassUnavailable) as error:
                if isinstance(error, HTTPError):
                    retryable = error.code in {429, 500, 502, 503, 504}
                    if error.code == 429:
                        retry_wait = 30
                    header = error.headers.get("Retry-After", "") if error.headers else ""
                    if header.isdigit():
                        retry_wait = max(retry_wait, int(header))
                    elif header:
                        try:
                            retry_wait = max(retry_wait, (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass
                    if error.code == 429 or header:
                        # Carry the server cooldown into the next stage even if this
                        # request has exhausted its retry allowance.
                        self.cooldown_until = time.monotonic() + retry_wait
                event.update(status="failed", error=f"{type(error).__name__}: {error}")
                LOGGER.warning("stage=%s request_failed %s", stage, event["error"])
                if not retryable or attempt == self.retries:
                    raise OverpassUnavailable(f"stage={stage} {event['error']}") from error
            finally:
                self.last_request = time.monotonic()
                event["elapsed_seconds"] = round(self.last_request - started, 3)
                append_json(self.cache_dir.parent / "requests.jsonl", event)
            remaining = retry_wait
            while remaining > 0:
                interval = min(60, remaining)
                time.sleep(interval)
                remaining -= interval

    @staticmethod
    def _validate(payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
            raise OverpassUnavailable("no_elements_in_response")
        if payload.get("remark"):
            raise OverpassUnavailable(f"overpass_remark: {payload['remark']}")

    def fetch(self, query, *, stage="unspecified"):
        return self._fetch(self.endpoint, urlencode({"data": query}).encode(), stage=stage)

    def fetch_geometry(self, osm_type, osm_id, *, stage):
        full_geometry_query(osm_type, str(osm_id))
        url = f"{CORE_API}/{osm_type}/{osm_id}/full.json"
        payload, source, cache = self._fetch(url, stage=stage)
        return osm_api_geometry(payload, osm_type, str(osm_id)), source, cache


def record_discovery(path, row, stage, radius, payload, source, cache):
    entry = {"recorded_at_utc": now(), "sample_id": row["sample_id"],
             "population_name": row["Population.name"], "latitude": float(row["Latitude"]),
             "longitude": float(row["Longitude"]), "discovery_stage": stage, "search_radius_m": radius,
             "retrieval_source": source, "raw_response_cache": str(cache),
             "osm_base_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
             "candidates": [{"osm_type": e.get("type"), "osm_id": str(e.get("id")),
                              "tags": e.get("tags", {}), "feature_class": classify_water_feature(e.get("tags", {}))}
                             for e in payload.get("elements", [])]}
    append_json(path, entry)
    return entry


def evaluate_lake(row, client, *, discovery_log=None, candidate_log=None, candidate_dir=None, max_candidates=3):
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")
    lat, lon = float(row["Latitude"]), float(row["Longitude"])
    result = {"sample_id": row["sample_id"], "population_name": row["Population.name"],
              "latitude": lat, "longitude": lon, "status": "no_polygon", "review_required": True,
              "query_date_utc": now(), "candidate_count": 0}
    candidates, attempted, errors, outcomes = {}, {}, [], []
    truncated = False
    searches = [(500, "nearby_500m", nearby_lake_query(lat, lon, 500)),
                (0, "containing_area", containing_lake_query(lat, lon)),
                (2000, "nearby_2000m", nearby_lake_query(lat, lon, 2000))]
    for radius, stage, query in searches:
        try:
            payload, source, discovery_cache = client.fetch(query, stage=stage)
        except OverpassUnavailable as error:
            errors.append({"stage": stage, "kind": "retrieval_failed", "error": str(error)})
            if "request_budget_exhausted" in str(error):
                break
            continue
        if discovery_log is not None:
            record_discovery(discovery_log, row, stage, radius, payload, source, discovery_cache)
        for e in payload["elements"]:
            candidates[(str(e.get("type")), str(e.get("id")))] = e
        ranked = [c for c in rank_tag_candidates(candidates.values(), "lake") if c.feature_class in ALLOWED]
        result.update(candidate_count=len(candidates), search_radius_m=radius, discovery_stage=stage)
        matches = []
        for candidate in ranked[:max_candidates]:
            identity = (candidate.osm_type, candidate.osm_id)
            if identity in attempted:
                match = attempted[identity]
                if match is not None:
                    matches.append(match)
                continue
            attempted[identity] = None
            outcome = {"sample_id": row["sample_id"], "discovery_stage": stage, "osm_type": identity[0],
                       "osm_id": identity[1], "discovery_tags": candidate.tags, "recorded_at_utc": now()}
            try:
                if hasattr(client, "fetch_geometry"):
                    obj, shape_source, cache = client.fetch_geometry(*identity, stage=f"{stage}:geometry:{identity[0]}/{identity[1]}")
                else:  # Compatibility with offline query fixtures.
                    whole, shape_source, cache = client.fetch(full_geometry_query(*identity), stage="geometry")
                    obj = next((e for e in whole["elements"] if str(e["id"]) == identity[1] and e["type"] == identity[0]), None)
                    if obj is None:
                        raise ValueError("selected_object_missing")
                polygons = complete_polygon(obj)
                inside = contains(polygons, lon, lat)
                tags = obj.get("tags", {})
                feature_class = classify_water_feature(tags)
                evidence = name_agreement(row["Population.name"], tags)
                status = "containing_candidate" if inside else "point_outside_polygon"
                if feature_class not in ALLOWED:
                    status = "current_tags_excluded"
                outcome.update(status=status, point_inside_polygon=inside, name_evidence=evidence,
                               tags=tags, feature_class=feature_class, geometry_cache=str(cache),
                               retrieval_source=shape_source, geometry_api="core_osm" if hasattr(client, "fetch_geometry") else "overpass",
                               osm_version=obj.get("version"), osm_timestamp=obj.get("timestamp"))
                geometry = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
                feature = {"type": "Feature", "id": f"{identity[0]}/{identity[1]}", "properties": dict(outcome), "geometry": geometry}
                if candidate_dir is not None:
                    atomic_json(candidate_dir / f"{row['sample_id']}_{identity[0]}_{identity[1]}.geojson", feature)
                if inside and feature_class in ALLOWED:
                    metrics = polygon_metrics(polygons)
                    match = (evidence != "name_agrees", candidate, obj, outcome, feature, metrics)
                    attempted[identity] = match
                    matches.append(match)
            except (ValueError, OverpassUnavailable) as error:
                outcome.update(status="retrieval_failed" if isinstance(error, OverpassUnavailable) else "invalid_geometry", error=str(error))
                errors.append({"stage": stage, "kind": outcome["status"], "object": f"{identity[0]}/{identity[1]}", "error": str(error)})
            outcomes.append(outcome)
            if candidate_log is not None:
                append_json(candidate_log, outcome)
        truncated = truncated or len(ranked) > max_candidates
        if matches:
            matches.sort(key=lambda item: item[0])
            _, candidate, obj, outcome, feature, metrics = matches[0]
            result.update(metrics)
            result.update(status="candidate_polygon", osm_type=candidate.osm_type, osm_id=candidate.osm_id,
                          osm_name=obj.get("tags", {}).get("name", ""), osm_waterbody_type=outcome["feature_class"],
                          osm_tags=obj.get("tags", {}), point_inside_polygon=True, name_evidence=outcome["name_evidence"],
                          geometry_cache=outcome["geometry_cache"], retrieval_source=outcome["retrieval_source"],
                          geometry_api=outcome["geometry_api"], osm_version=obj.get("version"), osm_timestamp=obj.get("timestamp"),
                          ambiguity_flag=len(matches) > 1 or truncated or bool(errors))
            result["diagnostics"] = json.dumps({"errors": errors, "candidate_outcomes": outcomes,
                                                "other_containing_candidates": len(matches) - 1, "candidate_limit_reached": truncated})
            feature["properties"] = dict(result)
            return result, feature
    retrieval_errors = any(e["kind"] == "retrieval_failed" for e in errors)
    result["status"] = (("retrieval_failed" if getattr(client, "live", True) else "cache_missing") if retrieval_errors
                        else "unresolved" if errors or truncated else "no_polygon")
    result["diagnostics"] = json.dumps({"errors": errors, "candidate_outcomes": outcomes, "candidate_limit_reached": truncated})
    return result, None


FIELDS = ["sample_id", "population_name", "latitude", "longitude", "osm_type", "osm_id", "osm_name", "osm_waterbody_type",
          "osm_tags", "search_radius_m", "discovery_stage", "candidate_count", "point_inside_polygon", "name_evidence",
          "ambiguity_flag", "lake_area_m2", "lake_perimeter_m", "lake_area_perimeter_m", "lake_shoreline_development",
          "status", "review_required", "diagnostics", "geometry_api", "retrieval_source", "query_date_utc", "osm_version", "osm_timestamp", "geometry_cache"]


def run_sites(rows, source, output_dir, *, live=False, delay=2., timeout=30., max_failures=3,
              endpoint=ENDPOINT, retries=1, max_requests=320, max_candidates=3, resume=True):
    output_dir = Path(output_dir)
    if max_failures < 1 or max_candidates < 1:
        raise ValueError("failure and candidate limits must be positive")
    config = {"pipeline_version": PIPELINE_VERSION, "input_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
              "selected_ids": [r["sample_id"] for r in rows], "endpoint": endpoint, "geometry_endpoint": CORE_API,
              "max_candidates": max_candidates, "discovery_order": ["nearby_500m", "containing_area", "nearby_2000m"]}
    manifest = output_dir / "selection_manifest.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) != config:
        raise ValueError("output manifest differs; use a new output directory")
    atomic_json(manifest, config)
    client = CacheClient(output_dir / "raw_responses", live, delay, timeout, endpoint, retries, max_requests)
    results, features = [], []
    failures = 0
    prior_requests = sum(1 for line in (output_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()) if (output_dir / "requests.jsonl").exists() else 0
    metadata = {**config, "source": str(Path(source).resolve()), "live": live, "request_delay_seconds": delay,
                "timeout_seconds": timeout, "retries": retries, "max_requests": max_requests,
                "area_method": "spherical WGS84 approximation, full object, islands subtracted",
                "perimeter_method": "great-circle ring segments, including islands", "depth_equation": "pending_user_thesis"}

    def checkpoint_outputs(stopped=False):
        dest = output_dir / "lake_polygon_pilot.csv"
        temp = dest.with_suffix(".csv.tmp")
        with temp.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            for result in results:
                writer.writerow({**result, "osm_tags": json.dumps(result.get("osm_tags", {}), ensure_ascii=False)})
        temp.replace(dest)
        atomic_json(output_dir / "lake_polygon_pilot.geojson", {"type": "FeatureCollection", "features": features})
        atomic_json(output_dir / "run_metadata.json", {**metadata, "processed": len(results), "polygon_candidates": len(features),
                    "network_requests_this_run": client.request_count, "stopped_for_errors": stopped,
                    "network_requests_total_logged": prior_requests + client.request_count,
                    "unprocessed_ids": [r["sample_id"] for r in rows[len(results):]], "updated_at_utc": now()})

    for index, row in enumerate(rows, 1):
        saved = output_dir / "checkpoints" / f"{row['sample_id']}.json"
        previous = json.loads(saved.read_text(encoding="utf-8")) if resume and saved.exists() else None
        if previous and previous["result"]["status"] not in {"retrieval_failed", "cache_missing"}:
            result, feature = previous["result"], previous["feature"]
            LOGGER.info("lake=%s resume_checkpoint status=%s", row["sample_id"], result["status"])
        else:
            LOGGER.info("lake=%s progress=%d/%d", row["sample_id"], index, len(rows))
            result, feature = evaluate_lake(row, client, discovery_log=output_dir / "candidate_discovery.jsonl",
                                          candidate_log=output_dir / "candidate_outcomes.jsonl",
                                          candidate_dir=output_dir / "candidate_polygons", max_candidates=max_candidates)
            atomic_json(saved, {"result": result, "feature": feature})
        results.append(result)
        if feature:
            features.append(feature)
        failures = failures + 1 if result["status"] == "retrieval_failed" else 0
        stopped = live and (failures >= max_failures or client.request_count >= max_requests)
        checkpoint_outputs(stopped)
        LOGGER.info("lake=%s finished status=%s polygons=%d", row["sample_id"], result["status"], len(features))
        if stopped:
            LOGGER.error("stopped after network failures or request budget; checkpoints retained")
            break
    return results
