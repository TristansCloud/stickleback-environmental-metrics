import hashlib
import json
from pathlib import Path
import time

import ee

project = "stickleback-507923"
parent = f"projects/{project}/assets/stickleback_validation"
path = Path("lookup_overlay.geojson")
raw = path.read_bytes()
digest = hashlib.sha256(raw).hexdigest()[:16]
asset = f"{parent}/ee_closest_water_v1_{digest}"
features = json.loads(raw)["features"]
ids = {f["properties"]["sample_id"] for f in features if f["properties"]["role"] == "status"}
assert len(ids) == 599
ee.Initialize(project=project)
record = Path("lookup_overlay_upload.json")
if record.exists():
    previous = json.loads(record.read_bytes())
    if previous["asset"] != asset:
        raise ValueError("Existing upload record is for a different overlay")
    task_id = previous["task"]
else:
    converted = []
    for f in features:
        geom = f["geometry"]
        kwargs = {} if geom["type"] == "Point" else {"geodesic": False}
        props = {k: v for k, v in f["properties"].items() if v is not None}
        props["lookup_release"] = digest
        converted.append(ee.Feature(ee.Geometry(geom, "EPSG:4326", **kwargs), props))
    task = ee.batch.Export.table.toAsset(collection=ee.FeatureCollection(converted),
                                        description=f"closest_water_{digest}", assetId=asset)
    task.start()
    task_id = task.id
    record.write_text(json.dumps({"asset": asset, "task": task_id}), encoding="utf-8")
print(asset, task_id, len(features), flush=True)
for attempt in range(30):
    task_status = ee.data.getTaskStatus(task_id)[0]
    state = task_status["state"]
    if state == "COMPLETED":
        break
    if state not in {"READY", "RUNNING"}:
        raise RuntimeError(task_status)
    time.sleep(10)
else:
    raise TimeoutError("Export is still running")

fc = ee.FeatureCollection(asset)
checks = ee.Dictionary({"total": fc.size(),
                        "status_sites": fc.filter(ee.Filter.eq("role", "status")).aggregate_count_distinct("sample_id"),
                        "release": fc.filter(ee.Filter.eq("lookup_release", digest)).size()}).getInfo()
assert checks == {"total": len(features), "status_sites": 599, "release": len(features)}, checks
print("Verified", checks, flush=True)
old = f"{parent}/ee_full_review_v1_3d571ff57e659c91"
for name in ("sites", "lake_candidates", "river_candidates", "shoreline_samples"):
    print("Existing public-read", name, ee.data.getAssetAcl(f"{old}/{name}").get("all_users_can_read", False), flush=True)
