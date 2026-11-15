"""Fetch only study search bounds from the approved ArcGIS OSM replicas."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from enviro_data.osm_disk import require_space
from shapely.geometry import box, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.strtree import STRtree

repo = Path(sys.argv[1])
cache = Path("osm_replica_cache")
cache.mkdir(exist_ok=True)
with (repo / "data/ee_full_review/source_2026-11-01/stickleback_full_review_v1.csv").open(encoding="utf-8-sig", newline="") as f:
    sites = list(csv.DictReader(f))
coverage = json.loads((repo / "data/cache/geofabrik/study_coverage.json").read_bytes())
regions = {row["sample_id"]: row["regions"] for row in coverage["assignments"]}
na = "https://services6.arcgis.com/Do88DoK2xjTUCXd1/arcgis/rest/services/"
eu = "https://services-eu1.arcgis.com/zci5bUiJ8olAal7N/arcgis/rest/services/"
asia = "https://services-ap1.arcgis.com/iA7fZQOnjY9D67Zx/arcgis/rest/services/"
layers = {
    "NA": {"channel": na + "OSM_NA_Waterways", "polygon": na + "OSM_NA_Water"},
    "EU": {"channel": eu + "OpenStreetMap_Waterways_for_Europe", "polygon": eu + "OpenStreetMap_Water_Bodies_for_Europe"},
    "AS": {"channel": asia + "OSM_AS_Waterways"},
}

def site_box(row):
    lat, lon = float(row["latitude"]), float(row["longitude"])
    dy = 1520 / 111195
    dx = dy / math.cos(math.radians(lat))
    return box(max(-180, lon-dx), lat-dy, min(180, lon+dx), lat+dy)

def query(layer, group):
    area = unary_union([site_box(row) for row in group])
    polygons = [area] if area.geom_type == "Polygon" else list(area.geoms)
    rings = []
    for poly in polygons:
        poly = orient(poly, sign=-1)
        rings.extend([[(round(x, 7), round(y, 7)) for x,y in ring.coords]
                      for ring in [poly.exterior, *poly.interiors]])
    args = {"f": "geojson", "where": "1=1", "outFields": "*", "outSR": 4326, "inSR": 4326,
            "geometryType": "esriGeometryPolygon", "geometry": json.dumps({"rings": rings}, separators=(",", ":"))}
    url = layer + "/FeatureServer/0/query?" + urlencode(args)
    path = cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_bytes())["features"]
    req = Request(url, headers={"User-Agent": "stickleback-environmental-metrics/0.1"})
    with urlopen(req, timeout=28) as response:
        raw = response.read(16_000_001)
    if len(raw) > 16_000_000:
        raise ValueError("Response exceeds cache item limit")
    parsed = json.loads(raw)
    if parsed.get("error") or parsed.get("type") != "FeatureCollection":
        raise ValueError(str(parsed.get("error", "Invalid ArcGIS response"))[:220])
    if parsed.get("exceededTransferLimit") or (parsed.get("properties") or {}).get("exceededTransferLimit"):
        raise ValueError("ArcGIS transfer limit")
    require_space(cache, len(raw))
    with tempfile.NamedTemporaryFile(dir=cache, suffix=".part", delete=False) as file:
        file.write(raw)
        partial = Path(file.name)
    partial.replace(path)
    return parsed["features"]

groups = defaultdict(list)
for row in sites:
    if row["working_waterbody_type"] == "marine" and "pelagic" in row["population_name"].lower().split():
        continue
    assigned = set()
    for name in regions.get(row["sample_id"], []):
        assigned.update(("NA",) if name in {"us", "canada", "greenland"} else ("AS",) if name == "japan"
                        else ("EU", "AS") if name in {"russia", "turkey"} else ("EU",))
    for area in sorted(assigned):
        for family, layer in layers[area].items():
            if (row["working_waterbody_type"], family) not in {("stream", "polygon"), ("lake", "channel")}:
                groups[(family, layer)].append(row)

def collect(family, layer, group):
    try:
        features = [f for f in query(layer, group) if f.get("geometry")]
        tree = STRtree([shape(f["geometry"]) for f in features])
        return [(row["sample_id"], family, layer,
                 [features[j] for j in tree.query(site_box(row), predicate="intersects")], None) for row in group]
    except Exception as exc:
        if len(group) > 1 and any(reason in str(exc).lower()
                                  for reason in ("limit", "exceeds", "404", "timed out", "414")):
            mid = len(group)//2
            return collect(family, layer, group[:mid]) + collect(family, layer, group[mid:])
        return [(row["sample_id"], family, layer, [], str(exc)) for row in group]

jobs = [(family, layer, rows[i:i+12]) for (family, layer), rows in groups.items() for i in range(0, len(rows), 12)]
print(f"Approved replica batch groups: {len(jobs)}", flush=True)
results = defaultdict(list)
with ThreadPoolExecutor(max_workers=6) as executor:
    futures = [executor.submit(collect, *job) for job in jobs]
    for i, future in enumerate(as_completed(futures), 1):
        for sid, family, layer, features, error in future.result():
            results[sid].append({"family": family, "layer": layer, "features": features, "error": error})
        if i % 10 == 0 or i == len(jobs):
            print(f"{i}/{len(jobs)} replica groups processed", flush=True)
payload = json.dumps(results, ensure_ascii=False).encode("utf-8")
require_space(cache, len(payload))
(cache / "site_features.json").write_bytes(payload)
print(f"sites={len(results)} error_sites={sum(any(q['error'] for q in v) for v in results.values())}", flush=True)
