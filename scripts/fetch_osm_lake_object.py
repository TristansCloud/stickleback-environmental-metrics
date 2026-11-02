"""Validate one known OSM water object against an input site; offline by default."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import Request

from enviro_data.lake_polygons import complete_polygon, contains, full_geometry_query, name_agreement, osm_api_geometry, polygon_metrics
from enviro_data.osm_http import bounded_urlopen as urlopen


def fetch(sample_id, osm_type, osm_id, output_dir, *, source=Path("site_overview_v1_clean.csv"), live=False):
    full_geometry_query(osm_type, str(osm_id))
    with source.open(encoding="utf-8-sig", newline="") as file:
        row = next(r for r in csv.DictReader(file) if r["sample_id"] == sample_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://api.openstreetmap.org/api/0.6/{osm_type}/{osm_id}/full.json"
    cache = output_dir / f"osm_api_{osm_type}_{osm_id}_full.json"
    retrieval = "cache"
    if not cache.exists():
        if not live:
            raise ValueError("cache missing; pass --live-osm for a known-object read")
        with urlopen(Request(url, headers={"User-Agent": "stickleback-environmental-metrics/0.1 (known lake object)"}), timeout=30) as response:
            data = response.read(8_000_001)
        if len(data) > 8_000_000:
            raise ValueError("response_exceeds_8MB")
        json.loads(data)  # Validate before caching.
        cache.write_bytes(data)
        retrieval = "network"
    obj = osm_api_geometry(json.loads(cache.read_text(encoding="utf-8")), osm_type, str(osm_id))
    polygons = complete_polygon(obj)
    inside = contains(polygons, float(row["Longitude"]), float(row["Latitude"]))
    result = {"sample_id": sample_id, "population_name": row["Population.name"],
              "latitude": float(row["Latitude"]), "longitude": float(row["Longitude"]),
              "source_url": url, "retrieval_source": retrieval, "osm_type": osm_type, "osm_id": str(osm_id),
              "tags": obj.get("tags", {}), "osm_version": obj.get("version"),
              "osm_timestamp": obj.get("timestamp"), "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "point_inside_polygon": inside, "name_evidence": name_agreement(row["Population.name"], obj.get("tags", {})),
              "status": "candidate_polygon" if inside else "point_outside_polygon", "review_required": True}
    if inside:
        result.update(polygon_metrics(polygons))
    (output_dir / f"osm_api_{osm_type}_{osm_id}_result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    geometry = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
    (output_dir / f"osm_api_{osm_type}_{osm_id}_polygon.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": result, "geometry": geometry}]}, ensure_ascii=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--osm-type", choices=("way", "relation"), required=True)
    parser.add_argument("--osm-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--input", type=Path, default=Path("site_overview_v1_clean.csv"))
    parser.add_argument("--live-osm", action="store_true")
    args = parser.parse_args()
    print(json.dumps(fetch(args.sample_id, args.osm_type, args.osm_id, args.output_dir, source=args.input, live=args.live_osm), ensure_ascii=True))
