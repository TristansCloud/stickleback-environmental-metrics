"""Bounded, cache-first OSM enrichment for pilot_sites_v1.csv (exactly 40 rows)."""
from __future__ import annotations
import argparse, csv, hashlib, json, logging, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from enviro_data.osm_matching import (
    OSMCandidate,
    OSMMatcher,
    build_habitat_overpass_query,
    build_ranked_geometry_query,
    match_ranked_tags,
    overpass_element_to_feature,
    rank_tag_candidates,
)
from enviro_data.site_habitat import infer_site_habitat

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "pilot_sites_v1.csv"
DEFAULT_DATA = ROOT / "data" / "osm_pilot"
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = "stickleback-environmental-metrics/0.1 (research pilot)"
LOGGER = logging.getLogger("pilot_osm")

def key_for(query): return hashlib.sha256(query.encode()).hexdigest()[:24]

def wait_for_request_slot(request_state, spacing_seconds):
    """Pause before every live Overpass request except the first one."""
    request_count = request_state.get("request_count", 0)
    if request_count and spacing_seconds > 0:
        time.sleep(spacing_seconds)
    request_state["request_count"] = request_count + 1


def fetch_one(lat, lon, radius, cache_dir, live, retries=0, sleep_seconds=2, coast_radius=10000.0, timeout_seconds=25.0, log_label="site", endpoint_state=None, endpoint_cooldown_seconds=300.0, query_override=None, parameters_override=None, request_state=None, request_spacing_seconds=1.0):
    started = time.monotonic()
    if query_override is None:
        raise ValueError("fetch_one requires an explicit bounded query")
    query = query_override; key = key_for(query); cache = cache_dir / f"{key}.json"
    parameters = parameters_override or {"lat": lat, "lon": lon, "radius_m": radius, "coast_radius_m": coast_radius}
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        LOGGER.info("%s retrieval=cache elements=%d elapsed=%.2fs", log_label, len(payload.get("elements", [])), time.monotonic() - started)
        return payload, {"source": "cache", "cache_file": str(cache), "query": query, "query_parameters": parameters, "elapsed_seconds": round(time.monotonic() - started, 3), "attempts": []}
    if not live:
        LOGGER.info("%s retrieval=unavailable reason=cache_miss_live_access_disabled", log_label)
        return None, {"source": "unavailable", "query": query, "query_parameters": parameters, "failure": "cache_miss_live_access_disabled", "elapsed_seconds": round(time.monotonic() - started, 3), "attempts": []}
    errors = []
    attempts = []
    endpoint_state = endpoint_state if endpoint_state is not None else {}
    request_state = request_state if request_state is not None else {}
    now = time.monotonic()
    available = [endpoint for endpoint in ENDPOINTS if endpoint_state.get(endpoint, {}).get("cooldown_until", 0) <= now]
    if not available:
        available = [min(ENDPOINTS, key=lambda endpoint: endpoint_state.get(endpoint, {}).get("cooldown_until", 0))]
    skipped = [endpoint for endpoint in ENDPOINTS if endpoint not in available]
    for endpoint in skipped:
        LOGGER.info("%s retrieval=skip endpoint=%s reason=cooldown", log_label, endpoint)
    available.sort(key=lambda endpoint: endpoint_state.get(endpoint, {}).get("failures", 0))
    for endpoint in available:
      for attempt in range(retries + 1):
        attempt_started = time.monotonic()
        LOGGER.info("%s retrieval=network endpoint=%s attempt=%d/%d", log_label, endpoint, attempt + 1, retries + 1)
        try:
            wait_for_request_slot(request_state, request_spacing_seconds)
            response = requests.post(endpoint, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=timeout_seconds)
            response.raise_for_status(); payload = response.json(); cache_dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            attempt_elapsed = round(time.monotonic() - attempt_started, 3)
            attempts.append({"endpoint": endpoint, "attempt": attempt + 1, "outcome": "success", "http_status": response.status_code, "elapsed_seconds": attempt_elapsed})
            endpoint_state[endpoint] = {"failures": 0, "cooldown_until": 0}
            LOGGER.info("%s retrieval=success endpoint=%s status=%d elements=%d elapsed=%.2fs", log_label, endpoint, response.status_code, len(payload.get("elements", [])), attempt_elapsed)
            return payload, {"source": "network", "endpoint": endpoint, "cache_file": str(cache), "query": query, "query_parameters": parameters, "elapsed_seconds": round(time.monotonic() - started, 3), "attempts": attempts}
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            attempt_elapsed = round(time.monotonic() - attempt_started, 3)
            outcome = f"HTTP {status}" if status else type(exc).__name__
            attempts.append({"endpoint": endpoint, "attempt": attempt + 1, "outcome": outcome, "http_status": status, "elapsed_seconds": attempt_elapsed})
            prior_failures = endpoint_state.get(endpoint, {}).get("failures", 0)
            endpoint_state[endpoint] = {"failures": prior_failures + 1, "cooldown_until": time.monotonic() + endpoint_cooldown_seconds}
            errors.append(f"{endpoint}: {type(exc).__name__}: HTTP {status}" if status else f"{endpoint}: {type(exc).__name__}: {exc}")
            LOGGER.warning("%s retrieval=failed endpoint=%s outcome=%s elapsed=%.2fs", log_label, endpoint, outcome, attempt_elapsed)
            if attempt < retries: time.sleep(sleep_seconds * (attempt + 1))
    LOGGER.error("%s retrieval=failed_all endpoints=%d elapsed=%.2fs", log_label, len(ENDPOINTS), time.monotonic() - started)
    return None, {"source": "failed", "query": query, "query_parameters": parameters, "failure": "; ".join(errors), "elapsed_seconds": round(time.monotonic() - started, 3), "attempts": attempts}


def search_radii(waterbody_type, general_ceiling=3000.0, coast_ceiling=10000.0, allow_expanded_search=False):
    radii = [100.0, 500.0]
    if allow_expanded_search:
        expanded_plans = {
            "lake": (min(1500.0, general_ceiling),),
            "stream": (min(1000.0, general_ceiling),),
            "marine": (min(3000.0, coast_ceiling), coast_ceiling),
            "transition": (min(1000.0, coast_ceiling), min(5000.0, coast_ceiling)),
            "unknown": (min(2000.0, general_ceiling),),
        }
        radii.extend(expanded_plans.get(waterbody_type, expanded_plans["unknown"]))
    return tuple(dict.fromkeys(radius for radius in radii if radius > 0))

def run(input_csv=DEFAULT_INPUT, data_dir=DEFAULT_DATA, live=False, radius=3000.0, coast_radius=10000.0, request_delay_seconds=1.0, timeout_seconds=25.0, retries=0, endpoint_cooldown_seconds=300.0, allow_expanded_search=False, retrieve_ranked_geometry=False):
    with input_csv.open(newline="", encoding="utf-8-sig") as fh: rows = list(csv.DictReader(fh))
    if len(rows) != 40: raise ValueError(f"expected exactly 40 pilot records, found {len(rows)}")
    cache_dir = data_dir / "raw_responses"; data_dir.mkdir(parents=True, exist_ok=True); output = data_dir / "pilot_osm_matches.csv"
    run_date = datetime.now(timezone.utc).isoformat()
    result_rows = []
    endpoint_state = {}
    request_state = {}
    LOGGER.info("run_start records=%d live=%s radius_m=%.1f coast_radius_m=%.1f timeout_s=%.1f retries=%d expanded_search=%s geometry_retrieval=%s", len(rows), live, radius, coast_radius, timeout_seconds, retries, allow_expanded_search, retrieve_ranked_geometry)
    for index, row in enumerate(rows, start=1):
        lat, lon = float(row["Latitude"]), float(row["Longitude"])
        inference = infer_site_habitat(row["Population.name"], row["Ecotype"])
        log_label = f"site={row['sample_id']} progress={index}/{len(rows)} type={inference.working_waterbody_type}"
        LOGGER.info("%s start", log_label)
        radii = search_radii(inference.working_waterbody_type, radius, coast_radius, allow_expanded_search)
        elements_by_id = {}
        candidates = []
        retrievals = []
        match = None
        search_stage = ""

        for stage_number, stage_radius in enumerate(radii, start=1):
            search_stage = f"stage_{stage_number}_of_{len(radii)}"
            stage_label = f"{log_label} stage={stage_number}/{len(radii)} radius_m={stage_radius:.0f} mode=tags"
            query = build_habitat_overpass_query(lat, lon, stage_radius, inference.working_waterbody_type)
            parameters = {"lat": lat, "lon": lon, "radius_m": stage_radius, "waterbody_type": inference.working_waterbody_type, "stage": stage_number, "response": "ids_and_tags"}
            payload, retrieval = fetch_one(lat, lon, stage_radius, cache_dir, live, retries=retries, coast_radius=stage_radius, timeout_seconds=timeout_seconds, log_label=stage_label, endpoint_state=endpoint_state, endpoint_cooldown_seconds=endpoint_cooldown_seconds, query_override=query, parameters_override=parameters, request_state=request_state, request_spacing_seconds=request_delay_seconds)
            retrievals.append(retrieval)
            if payload is None:
                break
            for element in payload.get("elements", []):
                elements_by_id[(str(element.get("type", "")), str(element.get("id", "")))] = element
            candidates = rank_tag_candidates(elements_by_id.values(), inference.working_waterbody_type)
            match = match_ranked_tags(row["sample_id"], candidates, inference.working_waterbody_type, stage_radius)
            if match.osm_id:
                break

        selected = candidates[0] if match and match.osm_id and candidates else None
        if selected and retrieve_ranked_geometry:
            geometry_query = build_ranked_geometry_query(selected.osm_type, selected.osm_id, lat, lon, stage_radius)
            geometry_label = f"{log_label} selected={selected.osm_type}/{selected.osm_id} mode=geometry"
            geometry_parameters = {"lat": lat, "lon": lon, "radius_m": stage_radius, "osm_type": selected.osm_type, "osm_id": selected.osm_id, "response": "clipped_geometry"}
            geometry_payload, geometry_retrieval = fetch_one(lat, lon, stage_radius, cache_dir, live, retries=retries, coast_radius=stage_radius, timeout_seconds=timeout_seconds, log_label=geometry_label, endpoint_state=endpoint_state, endpoint_cooldown_seconds=endpoint_cooldown_seconds, query_override=geometry_query, parameters_override=geometry_parameters, request_state=request_state, request_spacing_seconds=request_delay_seconds)
            retrievals.append(geometry_retrieval)
            geometry_elements = (geometry_payload or {}).get("elements", [])
            if geometry_elements:
                geometry_candidate = OSMCandidate.from_feature(overpass_element_to_feature(geometry_elements[0]))
                geometry_match = OSMMatcher([geometry_candidate], search_radius_m=stage_radius).match(row["sample_id"], lat, lon, inference.working_waterbody_type)
                if geometry_match.osm_id:
                    selected, match = geometry_candidate, geometry_match

        sources = [item["source"] for item in retrievals]
        query_source = "network" if "network" in sources else "cache" if "cache" in sources else sources[-1]
        endpoints = list(dict.fromkeys(item.get("endpoint", "") for item in retrievals if item.get("endpoint")))
        attempts = [attempt for item in retrievals for attempt in item["attempts"]]
        failures = [item["failure"] for item in retrievals if item.get("failure")]
        retrieval_elapsed = round(sum(item["elapsed_seconds"] for item in retrievals), 3)
        diagnostics = {"retrieval_failures": failures, "match": match.diagnostics if match else {}}
        out = {"sample_id": row["sample_id"], "population_name": row["Population.name"], "ecotype": row["Ecotype"], "working_waterbody_type": inference.working_waterbody_type, "name_inference_matched_terms": ";".join(inference.matched_terms), "latitude": lat, "longitude": lon, "osm_query_date": run_date, "search_stage": search_stage, "search_radii_m": json.dumps(radii), "query_source": query_source, "retrieval_endpoint": ";".join(endpoints), "retrieval_elapsed_seconds": retrieval_elapsed, "retrieval_attempts": json.dumps(attempts, sort_keys=True), "query_parameters": json.dumps([item["query_parameters"] for item in retrievals], sort_keys=True), "candidate_count": len(candidates), "selected_osm_type": selected.osm_type if selected else "", "selected_osm_id": match.osm_id if match else "", "selected_osm_tags": json.dumps(dict(match.tags), ensure_ascii=False, sort_keys=True) if match else "", "water_feature_class": match.feature_class if match else "", "match_method": match.match_method if match else "unavailable", "match_distance_m": match.distance_m if match else "", "manual_review": (match.review_required if match else False) or inference.manual_review or bool(failures), "failure_diagnostics": json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)}
        result_rows.append(out)
        LOGGER.info("%s complete candidates=%d match=%s osm=%s/%s distance_m=%s review=%s", log_label, len(candidates), out["match_method"], out["selected_osm_type"] or "-", out["selected_osm_id"] or "-", out["match_distance_m"] if out["match_distance_m"] != "" else "-", out["manual_review"])
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(result_rows[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(result_rows)
    metadata = {"run_date": run_date, "input": str(input_csv), "record_count": len(rows), "live_network_enabled": live, "expanded_search_enabled": allow_expanded_search, "ranked_geometry_retrieval_enabled": retrieve_ranked_geometry, "general_radius_ceiling_m": radius, "coast_radius_ceiling_m": coast_radius, "search_plans_m": {kind: search_radii(kind, radius, coast_radius, allow_expanded_search) for kind in ("lake", "stream", "marine", "transition", "unknown")}, "request_delay_seconds": request_delay_seconds, "timeout_seconds": timeout_seconds, "retries": retries, "endpoint_cooldown_seconds": endpoint_cooldown_seconds, "request_method": "POST", "query_strategy": "100 m then 500 m ID/tag discovery and habitat-aware ranking; optional selected clipped-geometry retrieval and expanded retries", "alternate_endpoints": list(ENDPOINTS), "output": str(output)}
    (data_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    LOGGER.info("run_complete records=%d retrieved=%d matched=%d unavailable=%d review=%d", len(result_rows), sum(row["query_source"] in {"cache", "network"} for row in result_rows), sum(bool(row["selected_osm_id"]) for row in result_rows), sum(row["match_method"] == "unavailable" for row in result_rows), sum(bool(row["manual_review"]) for row in result_rows))
    return result_rows

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, default=DEFAULT_INPUT); parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA); parser.add_argument("--live-osm", action="store_true", help="explicitly permit bounded Overpass requests for the 40 pilot rows"); parser.add_argument("--radius-m", type=float, default=3000.0); parser.add_argument("--coast-radius-m", type=float, default=10000.0); parser.add_argument("--allow-expanded-search", action="store_true", help="retry unmatched sites beyond 500 m using the habitat-specific legacy limits"); parser.add_argument("--retrieve-ranked-geometry", action="store_true", help="retrieve clipped geometry for the top tag-ranked candidate"); parser.add_argument("--request-delay-seconds", type=float, default=1.0); parser.add_argument("--timeout-seconds", type=float, default=25.0); parser.add_argument("--retries", type=int, default=0); parser.add_argument("--endpoint-cooldown-seconds", type=float, default=300.0); parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"); args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)sZ %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    rows = run(args.input, args.data_dir, args.live_osm, args.radius_m, args.coast_radius_m, args.request_delay_seconds, args.timeout_seconds, args.retries, args.endpoint_cooldown_seconds, args.allow_expanded_search, args.retrieve_ranked_geometry)
    from collections import Counter
    print(json.dumps({"records": len(rows), "sources": Counter(r["query_source"] for r in rows), "matched": sum(bool(r["selected_osm_id"]) for r in rows), "manual_review": sum(r["manual_review"] is True or r["manual_review"] == "True" for r in rows), "unavailable": sum(r["match_method"] == "unavailable" for r in rows)}, default=str))
