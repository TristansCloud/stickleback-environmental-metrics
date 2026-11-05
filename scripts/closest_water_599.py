"""Rule-based water lookup for the frozen Stickleback review sites."""
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import sys

from shapely.affinity import scale
from shapely.geometry import Point, LineString, Polygon, shape, box, mapping
from shapely.ops import nearest_points
from shapely.strtree import STRtree
from enviro_data.lake_polygons import name_agreement, polygon_metrics

repo = Path(sys.argv[1])
retry_radius = int(sys.argv[3]) if len(sys.argv) > 3 else 500
lake_nearshore_m = 500
work = Path.cwd()
output = work / "outputs"
output.mkdir(exist_ok=True)
data = repo / "data/ee_full_review"
release = data / "ee_full_review_v1_3d571ff57e659c91"
site_table = Path(sys.argv[5]) if len(sys.argv) > 5 else data / "source_2026-11-01/stickleback_full_review_v1.csv"
with site_table.open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
assert len({r["sample_id"] for r in rows}) == len(rows) == 599
coverage = json.loads((repo / "data/cache/geofabrik/study_coverage.json").read_bytes())
regions = {r["sample_id"]: r["regions"] for r in coverage["assignments"]}

def location(row):
    return float(row["longitude"]), float(row["latitude"])

def pelagic(row):
    return row["working_waterbody_type"] == "marine" and "pelagic" in row["population_name"].lower().split()

def search_box(row):
    x, y = location(row)
    dx = (retry_radius + 10) / (111195 * math.cos(math.radians(y)))
    dy = (retry_radius + 10) / 111195
    return box(max(-180, x-dx), y-dy, min(180, x+dx), y+dy)

def classify(p, geom):
    linear = geom.geom_type in {"LineString", "MultiLineString"}
    polygon = geom.geom_type in {"Polygon", "MultiPolygon"}
    water = p.get("water")
    natural = p.get("natural") or p.get("natural_") or p.get("nat")
    if linear and (p.get("waterway") in {"river", "stream", "tidal_channel"} or p.get("reach_id")):
        return "channel"
    if linear and natural == "coastline":
        return "coast"
    if polygon and (natural == "wetland" or p.get("wetland")):
        return "wetland"
    if polygon and (water in {"river", "stream"} or p.get("waterway") == "riverbank"):
        return "river_polygon"
    if polygon and (water in {"lagoon", "estuary", "bay"} or natural == "bay"):
        return "coastal_water"
    if polygon and (water in {"lake", "pond", "reservoir"} or (natural == "water" and not water) or p.get("frozen_lake")):
        return "inland_water"

def record(f, source, key=None):
    if not f.get("geometry"):
        return
    geom = shape(f["geometry"])
    if geom.is_empty or not geom.is_valid:
        return
    p = f["properties"]
    kind = classify(p, geom)
    key = key or p.get("osm_id2") or p.get("osm_id")
    if kind and key:
        return (kind, source, str(key), p.get("name") or p.get("name_en") or "", geom)

by_site = defaultdict(list)
replica = {}
if len(sys.argv) > 4:
    replica = json.loads(Path(sys.argv[4]).read_bytes())
    for sid, queries in replica.items():
        for query in queries:
            for feature in query["features"]:
                props = feature["properties"]
                if query["family"] == "polygon" and not any(props.get(tag) for tag in ("natural", "natural_", "nat")):
                    props["natural"] = "water"
                if (candidate := record(feature, "OSM via Esri")):
                    by_site[sid].append(candidate)
iceland = [row for row in rows if "iceland" in regions.get(row["sample_id"], []) and not pelagic(row)]
iceland_dir = None if sys.argv[2] == "-" else Path(sys.argv[2])
if iceland_dir is not None:
    import shapefile
    from rasterio.crs import CRS
areas = [search_box(row) for row in iceland]
area_index = STRtree(areas)
for name in ("gis_osm_waterways_free_1.shp", "gis_osm_water_a_free_1.shp") if iceland_dir else ():
    path = iceland_dir / name
    if CRS.from_wkt(path.with_suffix(".prj").read_text(encoding="utf8")).to_epsg() != 4326:
        raise ValueError("Expected an EPSG:4326 Iceland extract")
    with shapefile.Reader(str(path), encoding="utf8") as reader:
        for item in reader.iterShapeRecords():
            indexes = area_index.query(box(*item.shape.bbox))
            if not len(indexes):
                continue
            attrs = item.record.as_dict()
            category = attrs["fclass"]
            props = {"osm_id": attrs["osm_id"], "name": attrs["name"]}
            if category in {"stream", "river"} and "waterways" in name:
                props["waterway"] = category
            elif category in {"water", "reservoir"} and "water_a" in name:
                props["natural"] = "water"
            else:
                continue
            candidate = record({"geometry": item.shape.__geo_interface__, "properties": props}, "Geofabrik Iceland (2025)")
            if candidate:
                for index in indexes:
                    by_site[iceland[index]["sample_id"]].append(candidate)

for filename in ("lake_candidates", "river_candidates"):
    for f in json.loads((release / f"{filename}.geojson").read_bytes())["features"]:
        p = f["properties"]
        if filename == "lake_candidates":
            p["frozen_lake"] = True
            key = f"{p.get('osm_type')}/{p['osm_id']}" if p.get("osm_id") else p.get("hylak_id") or p["sample_id"]
            source = p.get("source") or "Frozen lake review"
        else:
            key = p.get("reach_id")
            source = "HydroRIVERS"
        if source == "HydroLAKES v1.0":
            continue
        if (item := record(f, source, key)):
            by_site[p["sample_id"]].append(item)

supplement = Path(sys.argv[6]) if len(sys.argv) > 6 else None
if supplement:
    for feature in json.loads(supplement.read_bytes())["features"]:
        p = feature["properties"]
        candidate = record(feature, p["source"], p["feature_id"])
        if candidate:
            by_site[p["sample_id"]].append(candidate)

for f in (repo / "data/cache/osm_map").glob("*.json"):
    elements = json.loads(f.read_bytes())["elements"]
    nodes = {n["id"]: (n["lon"], n["lat"]) for n in elements if n["type"] == "node"}
    for e in elements:
        p = e.get("tags", {})
        if e["type"] != "way" or not (p.get("waterway") or p.get("natural") in {"water", "wetland", "coastline", "bay"}):
            continue
        pts = [nodes[n] for n in e["nodes"]]
        if len(pts) < 2:
            continue
        geom = Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] and p.get("natural") in {"water", "wetland", "bay"} else LineString(pts)
        kind = classify(p, geom)
        if kind and geom.is_valid:
            for row in rows:
                if not pelagic(row) and search_box(row).intersects(geom):
                    by_site[row["sample_id"]].append((kind, "OSM map cache", f"way/{e['id']}", p.get("name", ""), geom))

eligible = {
    "stream": {"channel"},
    "lake": {"inland_water"},
    "marine": {"coast", "coastal_water"},
    "transition": {"channel", "coast", "coastal_water", "wetland", "river_polygon"},
    "unknown": {"channel", "coast", "coastal_water", "wetland", "river_polygon", "inland_water"},
}
results = []
lookup_features = []
merit_regions = []
atlas = {}
for row in rows:
    sid = row["sample_id"]
    lon, lat = location(row)
    point = Point(lon, lat)
    habitat = row["working_waterbody_type"]
    scored = defaultdict(list)
    if not pelagic(row):
        for kind, source, key, name, geom in by_site[sid]:
            if kind not in eligible[habitat]:
                continue
            xscale = 111195 * math.cos(math.radians(lat))
            metric = scale(geom.boundary if geom.geom_type.endswith("Polygon") else geom,
                           xfact=xscale, yfact=111195, origin=(lon, lat))
            nearest = nearest_points(point, metric)[1]
            distance = point.distance(nearest)
            if kind != "inland_water" and distance > retry_radius:
                continue
            inside = kind == "inland_water" and geom.covers(point)
            if kind == "inland_water" and not inside and (habitat != "lake" or distance > lake_nearshore_m):
                continue
            item = {"category": kind, "source": source, "feature_id": key, "feature_name": name,
                    "distance_m": round(distance, 2)}
            if kind == "inland_water":
                item["match_method"] = "contains_point" if inside else "nearshore_fallback"
                item["name_evidence"] = name_agreement(row["population_name"], {"name": name})
                item["review_required"] = not inside

            if habitat == "stream" and kind == "channel" and distance <= 500:
                item["proposed_snap_lon"] = lon + (nearest.x-lon)/xscale
                item["proposed_snap_lat"] = lat + (nearest.y-lat)/111195
            scored[kind].append((distance, source, key, item))
    first_pass = any(distance <= 500 or kind == "inland_water"
                     for kind, options in scored.items() for distance, *_ in options)
    selected = {}
    for kind, options in sorted(scored.items()):
        if kind == "inland_water":
            containing = [option for option in options if option[-1]["match_method"] == "contains_point"]
            options = containing or options
        if first_pass and kind != "inland_water":
            options = [option for option in options if option[0] <= 500]
        if options:
            selected[kind] = min(options, key=lambda option: option[:3])[-1]
    queries = replica.get(sid, [])
    expected = {"stream": "channel", "lake": "polygon"}.get(habitat)
    completed = [q["family"] for q in queries if not q["error"]]
    errors = [q["error"] for q in queries if q["error"]]
    status = ("pelagic_skipped" if pelagic(row) else "candidate_found" if selected
              else "no_eligible_candidate" if expected in completed and not errors
              else "source_coverage_incomplete")
    results.append({"sample_id": sid, "population_name": row["population_name"],
                    "original_lon": row["longitude"], "original_lat": row["latitude"], "habitat": habitat,
                    "status": status, "lookup_radius_m": None if pelagic(row) else 500 if first_pass else retry_radius,
                    "regional_extract_used": iceland_dir is not None and "iceland" in regions.get(sid, []) and not pelagic(row),
                    "replica_layers_completed": "|".join(sorted(set(completed))),
                    "replica_errors": " | ".join(dict.fromkeys(errors)),
                    "candidates": selected})
    if habitat == "stream":
        merit_regions.append({"type": "Feature", "geometry": mapping(point),
                              "properties": {"sample_id": sid, "method": "point_buffer_max_150m"}})
    elif habitat == "lake" and selected.get("inland_water"):
        chosen = selected["inland_water"]
        geometry = next(geom for kind, source, key, name, geom in by_site[sid]
                        if kind == "inland_water" and source == chosen["source"] and key == chosen["feature_id"])
        polygons = [[list(poly.exterior.coords), *[list(r.coords) for r in poly.interiors]]
                    for poly in ([geometry] if geometry.geom_type == "Polygon" else geometry.geoms)]
        shape_metrics = polygon_metrics(polygons)
        merit_regions.append({"type": "Feature", "geometry": mapping(geometry),
                              "properties": {"sample_id": sid, "method": "lake_polygon_max",
                                             "polygon_source": chosen["source"], "polygon_id": chosen["feature_id"],
                                             "lake_match_method": chosen["match_method"],
                                             "lake_shore_distance_m": chosen["distance_m"],
                                              "lake_name_evidence": chosen["name_evidence"],
                                             "lake_geometry_source": chosen["source"],
                                             "lake_geometry_status": "candidate_polygon",
                                             "lake_polygon_feature_id": chosen["feature_id"],
                                             **shape_metrics}})
    if not replica:
        continue
    extent = search_box(row)
    paths = []
    drawn = set()
    for kind, source, key, name, geom in by_site[sid]:
        identity = (kind, source, key)
        if identity in drawn:
            continue
        drawn.add(identity)
        winner = selected.get(kind)
        picked = bool(winner and (winner["source"], winner["feature_id"]) == (source, key))
        line = geom.boundary if geom.geom_type.endswith("Polygon") else geom
        clipped = line.intersection(extent).simplify(0.000035)
        pieces = [clipped] if clipped.geom_type == "LineString" else list(getattr(clipped, "geoms", []))
        coords = [[[round(x, 6), round(y, 6)] for x, y, *_ in p.coords]
                  for p in pieces if p.geom_type == "LineString" and not p.is_empty]
        if not coords:
            continue
        paths.append([kind, picked, coords])
        if picked:
            lookup_features.append({"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": coords},
                                    "properties": {"sample_id": sid, "role": kind, "feature_id": key, "source": source}})
    if sid in replica:
        x, y = location(row)
        dy = 1520 / 111195
        dx = dy / math.cos(math.radians(y))
        query_bounds = (max(-180, x-dx), y-dy, min(180, x+dx), y+dy)
        lookup_features.append({"type": "Feature", "geometry": mapping(box(*query_bounds).boundary),
                                "properties": {"sample_id": sid, "role": "query_box"}})
    else:
        query_bounds = None
    lookup_features.append({"type": "Feature", "geometry": mapping(point), "properties": {
        "sample_id": sid, "role": "status", "lookup_status": status, "lookup_radius_m": results[-1]["lookup_radius_m"],
        "lookup_summary": "\n".join(f"{kind}: {c['feature_name'] or c['feature_id']} ({c['distance_m']} m)"
                                   + (f" · {c['match_method']} · {c['name_evidence']}" if kind == "inland_water" else "")
                                   for kind, c in selected.items())}})
    atlas[sid] = {"name": row["population_name"], "habitat": habitat, "status": status,
                  "point": [lon, lat], "extent": extent.bounds, "query": query_bounds, "paths": paths}

summary = dict(Counter(r["status"] for r in results))
sources = ["Frozen Earth Engine review geometry", "Local OSM map boxes", "Local Iceland Geofabrik shapefiles"]
if replica:
    sources.extend(sorted({q["layer"] for queries in replica.values() for q in queries}))
report = {"sites": results, "summary": summary, "coverage": "Closest within evaluated candidates only. Replica does not supply global coastlines or Asian water polygons.",
          "sources": sources, "first_pass_radius_m": 500, "retry_radius_m": retry_radius, "lake_nearshore_m": lake_nearshore_m, "license": "OpenStreetMap contributors, ODbL; HydroRIVERS, HydroLAKES"}
fields = ["sample_id", "population_name", "original_lon", "original_lat", "habitat", "status",
          "lookup_radius_m", "regional_extract_used", "replica_layers_completed", "replica_errors"]
categories = sorted(set.union(*eligible.values()))
prefix = f"stickleback_nearshore_599_{'arcgis' if replica else 'local'}_{retry_radius}m"
with (output / f"{prefix}.csv").open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fields + categories + ["lake_match_method", "lake_name_evidence", "lake_review_required", "proposed_snap_lon", "proposed_snap_lat"])
    writer.writeheader()
    for r in results:
        details = {kind: f"{c['source']} {c['feature_id']} {c['feature_name']} ({c['distance_m']} m)"
                   for kind, c in r["candidates"].items()}
        snap = {k: v for k, v in r["candidates"].get("channel", {}).items() if k.startswith("proposed_")}
        lake = r["candidates"].get("inland_water", {})
        lake_evidence = {"lake_match_method": lake.get("match_method"),
                         "lake_name_evidence": lake.get("name_evidence"),
                         "lake_review_required": lake.get("review_required")}
        writer.writerow({**{k: r[k] for k in fields}, **details, **snap, **lake_evidence})
(output / f"{prefix}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(summary, flush=True)
if replica:
    (work / "lookup_overlay.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": lookup_features},
                                                            ensure_ascii=False), encoding="utf-8")
    (work / "lookup_atlas.json").write_text(json.dumps(atlas, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

(work / "merit_regions.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": merit_regions},
                                                       ensure_ascii=False), encoding="utf-8")
