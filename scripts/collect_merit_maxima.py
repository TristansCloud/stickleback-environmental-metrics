"""Cache native MERIT upstream-area maxima for stream buffers and lake polygons."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import time

import ee
from shapely.geometry import shape


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", type=Path, required=True)
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--lake-cell-budget", type=int, default=1_000_000)
    args = parser.parse_args()
    raw = args.regions.read_bytes()
    regions = json.loads(raw)["features"]
    if args.lake_cell_budget <= 0:
        parser.error("--lake-cell-budget must be positive")
    identity = {"regions_sha256": hashlib.sha256(raw).hexdigest(), "dataset": "MERIT/Hydro/v1_0_1",
                "band": "upa", "stream_radius_m": 150, "selection": "native_cell_centres",
                "lake_cell_budget": args.lake_cell_budget, "version": 2}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    target = args.output / digest
    target.mkdir(parents=True, exist_ok=True)
    ee.Initialize(project=args.project)
    image = ee.Image(identity["dataset"]).select("upa")
    projection = image.projection().getInfo()
    identity["projection"] = projection
    (target / "manifest.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    reducer = ee.Reducer.max().unweighted().combine(ee.Reducer.count(), sharedInputs=True)
    collected = {}
    bounded = []
    dx, _, x0, _, dy, y0 = projection["transform"]
    for feature in regions:
        props = feature["properties"]
        if props["method"] == "lake_polygon_max":
            west, south, east, north = shape(feature["geometry"]).bounds
            columns = math.ceil((east-x0)/dx)-math.floor((west-x0)/dx)+2
            rows = math.ceil((south-y0)/dy)-math.floor((north-y0)/dy)+2
            if rows*columns > args.lake_cell_budget:
                collected[props["sample_id"]] = {
                    "merit_max_upstream_area_km2": None, "merit_valid_cell_count": 0,
                    "merit_method": props["method"], "merit_status": "lake_pixel_budget_exceeded",
                    "merit_estimated_bbox_cells": rows*columns, "merit_polygon_id": props["polygon_id"],
                    "merit_polygon_source": props["polygon_source"],
                    "lake_match_method": props.get("lake_match_method"), "lake_shore_distance_m": props.get("lake_shore_distance_m"),
                    "lake_name_evidence": props.get("lake_name_evidence"),
                    "merit_dataset": identity["dataset"], "merit_release": digest}
                continue
        bounded.append(feature)
    regions = bounded
    print("Regions within budget", len(regions), "large lakes deferred", len(collected), flush=True)
    for offset in range(0, len(regions), 20):
        group = regions[offset:offset+20]
        checkpoint = target / f"batch_{offset:04d}.json"
        if checkpoint.exists():
            result = json.loads(checkpoint.read_bytes())
        else:
            features = []
            for f in group:
                geometry = f["geometry"]
                kwargs = {} if geometry["type"] == "Point" else {"geodesic": False}
                geom = ee.Geometry(geometry, "EPSG:4326", **kwargs)
                if f["properties"]["method"] == "point_buffer_max_150m":
                    geom = geom.buffer(150, 0.5)
                features.append(ee.Feature(geom, f["properties"]))
            reduced = image.reduceRegions(
                collection=ee.FeatureCollection(features), reducer=reducer,
                crs=projection["crs"], crsTransform=projection["transform"],
                maxPixelsPerRegion=args.lake_cell_budget, tileScale=2)
            # Return only properties, keeping polygon geometry out of client results.
            result = reduced.toList(len(group)).map(lambda f: ee.Feature(f).toDictionary()).getInfo()
            checkpoint.write_text(json.dumps(result, indent=2), encoding="utf-8")
        for p in result:
            value = p.get("upa_max", p.get("max"))
            count = p.get("upa_count", p.get("count", 0))
            collected[p["sample_id"]] = {
                "merit_max_upstream_area_km2": value, "merit_valid_cell_count": count,
                "merit_method": p["method"], "merit_status": "ok" if value is not None and count else "no_native_cells",
                "merit_polygon_id": p.get("polygon_id"), "merit_polygon_source": p.get("polygon_source"),
                "lake_match_method": p.get("lake_match_method"), "lake_shore_distance_m": p.get("lake_shore_distance_m"),
                "lake_name_evidence": p.get("lake_name_evidence"),
                "merit_dataset": identity["dataset"], "merit_release": digest}
        print(f"MERIT regions {min(offset+20,len(regions))}/{len(regions)}", flush=True)
    with args.sites.open(encoding="utf-8-sig", newline="") as file:
        sites = list(csv.DictReader(file))
    assert len(sites) == 599 and len({s["sample_id"] for s in sites}) == 599
    output = []
    for site in sites:
        sid = site["sample_id"]
        props = collected.get(sid, {
            "merit_max_upstream_area_km2": None, "merit_valid_cell_count": 0,
            "merit_method": None, "merit_status": "missing_lake_polygon" if site["working_waterbody_type"] == "lake" else "not_applicable",
            "merit_dataset": identity["dataset"], "merit_release": digest})
        output.append({"type": "Feature", "geometry": {"type": "Point",
                      "coordinates": [float(site["longitude"]),float(site["latitude"])]},
                      "properties": {"sample_id": sid, **props}})
    result_path = target / "merit_maxima.geojson"
    result_path.write_text(json.dumps({"type":"FeatureCollection","features":output},indent=2),encoding="utf-8")
    print(Counter(f["properties"]["merit_status"] for f in output),flush=True)
    print(result_path,flush=True)
    if not args.upload:
        return
    asset = f"projects/{args.project}/assets/stickleback_validation/merit_maxima_v1_{digest}"
    record = target / "upload.json"
    if record.exists():
        task_id = json.loads(record.read_bytes())["task"]
    else:
        converted = [ee.Feature(ee.Geometry.Point(f["geometry"]["coordinates"]),
                               {k:v for k,v in f["properties"].items() if v is not None}) for f in output]
        task = ee.batch.Export.table.toAsset(collection=ee.FeatureCollection(converted),
                                            description=f"merit_maxima_{digest}", assetId=asset)
        task.start()
        task_id = task.id
        record.write_text(json.dumps({"asset":asset,"task":task_id}),encoding="utf-8")
    print(asset,task_id,flush=True)
    for _ in range(30):
        status=ee.data.getTaskStatus(task_id)[0]
        if status["state"] == "COMPLETED":
            break
        if status["state"] not in {"READY","RUNNING"}:
            raise RuntimeError(status)
        time.sleep(10)
    else:
        raise TimeoutError("MERIT asset export is still running")
    fc=ee.FeatureCollection(asset)
    checks=ee.Dictionary({"rows":fc.size(),"sites":fc.aggregate_count_distinct("sample_id"),
                          "release":fc.filter(ee.Filter.eq("merit_release",digest)).size()}).getInfo()
    assert checks == {"rows":599,"sites":599,"release":599}, checks
    print("Verified MERIT asset",checks,flush=True)


if __name__ == "__main__":
    main()
