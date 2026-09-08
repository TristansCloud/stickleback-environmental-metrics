"""Bounded, cache-first OSM enrichment for pilot_sites_v1.csv (exactly 40 rows)."""
from __future__ import annotations
import argparse, csv, hashlib, json, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from enviro_data.osm_matching import OSMCandidate, OSMMatcher

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "pilot_sites_v1.csv"
DEFAULT_DATA = ROOT / "data" / "osm_pilot"
ENDPOINTS = ("https://overpass.kumi.systems/api/interpreter", "https://overpass.private.coffee/api/interpreter")

def query_for(lat, lon, radius):
    return f"[out:json];(way(around:{radius},{lat},{lon})[natural=water];way(around:{radius},{lat},{lon})[waterway];way(around:{radius},{lat},{lon})[landuse=reservoir];);out geom tags;"

def key_for(query): return hashlib.sha256(query.encode()).hexdigest()[:24]

def fetch_one(lat, lon, radius, cache_dir, live, retries=0, sleep_seconds=2):
    query = query_for(lat, lon, radius); key = key_for(query); cache = cache_dir / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8")), {"source": "cache", "cache_file": str(cache), "query": query, "query_parameters": {"lat": lat, "lon": lon, "radius_m": radius}}
    if not live:
        return None, {"source": "unavailable", "query": query, "query_parameters": {"lat": lat, "lon": lon, "radius_m": radius}, "failure": "cache_miss_live_access_disabled"}
    errors = []
    for endpoint in ENDPOINTS:
      for attempt in range(retries + 1):
        try:
            response = requests.get(endpoint, params={"data": query}, timeout=15)
            response.raise_for_status(); payload = response.json(); cache_dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            return payload, {"source": "network", "endpoint": endpoint, "cache_file": str(cache), "query": query, "query_parameters": {"lat": lat, "lon": lon, "radius_m": radius}}
        except Exception as exc:
            errors.append(f"{endpoint}: {type(exc).__name__}: {exc}")
            if attempt < retries: time.sleep(sleep_seconds * (attempt + 1))
    return None, {"source": "failed", "query": query, "query_parameters": {"lat": lat, "lon": lon, "radius_m": radius}, "failure": "; ".join(errors)}

def feature_from_element(element):
    geom = element.get("geometry", []); coords = [(p["lon"], p["lat"]) for p in geom]
    typ = "Polygon" if len(coords) >= 3 and coords[0] == coords[-1] else "LineString"
    return {"id": f"way/{element.get('id', '')}", "geometry": {"type": typ, "coordinates": [coords] if typ == "Polygon" else coords}, "tags": element.get("tags", {})}

def run(input_csv=DEFAULT_INPUT, data_dir=DEFAULT_DATA, live=False, radius=1000.0):
    with input_csv.open(newline="", encoding="utf-8-sig") as fh: rows = list(csv.DictReader(fh))
    if len(rows) != 40: raise ValueError(f"expected exactly 40 pilot records, found {len(rows)}")
    cache_dir = data_dir / "raw_responses"; data_dir.mkdir(parents=True, exist_ok=True); output = data_dir / "pilot_osm_matches.csv"
    run_date = datetime.now(timezone.utc).isoformat()
    result_rows = []
    for row in rows:
        lat, lon = float(row["Latitude"]), float(row["Longitude"])
        payload, retrieval = fetch_one(lat, lon, radius, cache_dir, live)
        candidates = [OSMCandidate.from_feature(feature_from_element(x)) for x in (payload or {}).get("elements", [])]
        match = OSMMatcher(candidates, search_radius_m=radius).match(row["sample_id"], lat, lon) if payload is not None else None
        selected = next((x for x in candidates if x.osm_id == match.osm_id), None) if match else None
        out = {"sample_id": row["sample_id"], "latitude": lat, "longitude": lon, "osm_query_date": run_date, "query_radius_m": radius, "query_source": retrieval["source"], "query_parameters": json.dumps(retrieval["query_parameters"], sort_keys=True), "candidate_count": len(candidates), "selected_osm_type": "way" if selected else "", "selected_osm_id": match.osm_id if match else "", "selected_osm_tags": json.dumps(dict(match.tags), ensure_ascii=False, sort_keys=True) if match else "", "water_feature_class": match.feature_class if match else "", "match_method": match.match_method if match else "unavailable", "match_distance_m": match.distance_m if match else "", "manual_review": match.review_required if match else False, "failure_diagnostics": json.dumps(retrieval.get("failure", "") or (match.diagnostics if match else ""), ensure_ascii=False, sort_keys=True)}
        result_rows.append(out)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(result_rows[0])); writer.writeheader(); writer.writerows(result_rows)
    metadata = {"run_date": run_date, "input": str(input_csv), "record_count": len(rows), "live_network_enabled": live, "radius_m": radius, "alternate_endpoints": list(ENDPOINTS), "output": str(output)}
    (data_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return result_rows

if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--input", type=Path, default=DEFAULT_INPUT); parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA); parser.add_argument("--live-osm", action="store_true", help="explicitly permit bounded Overpass requests for the 40 pilot rows"); parser.add_argument("--radius-m", type=float, default=1000.0); args = parser.parse_args()
    rows = run(args.input, args.data_dir, args.live_osm, args.radius_m)
    from collections import Counter
    print(json.dumps({"records": len(rows), "sources": Counter(r["query_source"] for r in rows), "matched": sum(bool(r["selected_osm_id"]) for r in rows), "manual_review": sum(r["manual_review"] is True or r["manual_review"] == "True" for r in rows), "unavailable": sum(r["match_method"] == "unavailable" for r in rows)}, default=str))
