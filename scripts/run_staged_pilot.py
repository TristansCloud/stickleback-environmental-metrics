"""Run the bounded 5-site gate, then the deterministic 40-site pilot.

The command is intentionally explicit about stage size.  It reads only a small
Copernicus window per site and makes one Earth Engine reduceRegion request per
site; it never exports or downloads MERIT rasters.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import platform
import sys
import time
import tracemalloc
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from enviro_data.dem_acquisition import RasterMetadata, retrieval_timestamp
from enviro_data.hydrology import delineate_catchment
from enviro_data.topography import extract_window

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "pilot_sites_v1.csv"
COPERNICUS_BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
BANDS = ("elv", "dir", "upa", "upg", "hnd", "wat", "wth")
LOG = logging.getLogger("enviro_data.staged_pilot")


def _rss_bytes() -> int | None:
    try:
        import psutil  # optional; intentionally not required for the pipeline
        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


class Metrics:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.peak_rss = _rss_bytes()
        tracemalloc.start()
        self.site_timings: list[dict[str, object]] = []
        self.source: dict[str, dict[str, float | int]] = {
            "copernicus": {"requests": 0, "cache_hits": 0, "cache_misses": 0, "elapsed_s": 0.0},
            "earth_engine": {"requests": 0, "cache_hits": 0, "cache_misses": 0, "elapsed_s": 0.0},
        }

    def finish(self) -> dict[str, object]:
        current, peak_alloc = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss = _rss_bytes()
        if rss is not None:
            self.peak_rss = max(self.peak_rss or 0, rss)
        return {
            "wall_time_s": round(time.perf_counter() - self.started, 6),
            "cpu_time_s": round(time.process_time() - self.cpu_started, 6),
            "peak_rss_bytes": self.peak_rss,
            "peak_python_alloc_bytes": peak_alloc,
            "current_python_alloc_bytes": current,
            "rss_metric": "psutil.Process().memory_info().rss" if self.peak_rss is not None else "unavailable_psutil_not_installed",
            "earth_engine_elapsed_definition": "client round-trip for reduceRegion.getInfo; excludes EE server compute/EECU",
            "sources": self.source,
            "sites": self.site_timings,
        }


def rows() -> list[dict[str, str]]:
    with PILOT.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def copernicus_url(latitude: float, longitude: float) -> str:
    lat, lon = int(latitude // 1), int(longitude // 1)
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    stem = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
    return f"{COPERNICUS_BUCKET}/{stem}/{stem}.tif"


def cache_dem(row: dict[str, str], metrics: Metrics) -> tuple[RasterMetadata, object, dict[str, object]]:
    try:
        import rasterio
        from rasterio.errors import RasterioIOError
        from rasterio.windows import Window
    except ImportError as exc:
        raise RuntimeError("staged DEM acquisition requires the 'terrain' extra") from exc
    site = row["sample_id"]
    url = copernicus_url(float(row["Latitude"]), float(row["Longitude"]))
    out = ROOT / "data" / "cache" / "staged_pilot" / f"{site}_copernicus_3x3.tif"
    sidecar = out.with_suffix(out.suffix + ".json")
    started = time.perf_counter()
    if site == "S0002" and (ROOT / "data/cache/stage_one_v2/S0002_copernicus_3x3.tif").is_file():
        source = ROOT / "data/cache/stage_one_v2/S0002_copernicus_3x3.tif"
        source_meta = source.with_suffix(source.suffix + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        if not out.is_file(): out.write_bytes(source.read_bytes())
        if not sidecar.is_file(): sidecar.write_bytes(source_meta.read_bytes())
    if out.is_file() and sidecar.is_file():
        metadata = RasterMetadata(**json.loads(sidecar.read_text(encoding="utf-8")))
        metadata.validate(out)
        metrics.source["copernicus"]["cache_hits"] += 1
        status = "cache_hit"
        with rasterio.open(out) as ds: values = ds.read(1)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        unavailable = False
        try:
            with rasterio.open("/vsicurl/" + url) as source:
                row_index, col_index = source.index(float(row["Longitude"]), float(row["Latitude"]))
                window = Window(max(0, col_index - 1), max(0, row_index - 1), 3, 3)
                values = source.read(1, window=window, boundless=True, masked=False).astype("float32")
                transform = source.window_transform(window)
                profile = source.profile.copy()
                profile.update(driver="GTiff", height=3, width=3, transform=transform, compress="deflate", nodata=-9999.0)
                if source.nodata is not None: values[values == source.nodata] = -9999.0
                source_crs = str(source.crs)
        except RasterioIOError as exc:
            # Some high-latitude/ocean tiles are absent from the public mirror.
            # Persist an explicit all-nodata fixture so absence is never treated
            # as sea-level elevation and remains visible in provenance.
            LOG.warning("source= copernicus site=%s unavailable=%s", site, exc)
            unavailable = True
            values = __import__("numpy").full((3, 3), -9999.0, dtype="float32")
            from rasterio.transform import from_origin
            profile = {"driver": "GTiff", "height": 3, "width": 3, "count": 1,
                       "dtype": "float32", "crs": "EPSG:4326", "transform": from_origin(float(row["Longitude"]), float(row["Latitude"]), 1/3600, 1/3600), "nodata": -9999.0}
            source_crs = "EPSG:4326"
        with rasterio.open(out, "w", **profile) as target: target.write(values, 1)
        metadata = RasterMetadata(url, f"GLO30:{site}", "Copernicus DEM AWS Open Data", retrieval_timestamp(),
                                  hashlib.sha256(out.read_bytes()).hexdigest(), source_crs,
                                  "EGM2008 (provider metadata)", 30.0, str(out), nodata=-9999.0,
                                  zero_is_ocean_nodata=False)
        metadata.validate(out)
        sidecar.write_text(json.dumps(asdict(metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        metrics.source["copernicus"]["cache_misses"] += 1
        metrics.source["copernicus"]["requests"] += 1
        status = "source_unavailable_nodata" if unavailable else "acquired"
    metrics.source["copernicus"]["elapsed_s"] += time.perf_counter() - started
    return metadata, values, {"status": status, "path": str(out), "source_url": url}


def merit(row: dict[str, str], metrics: Metrics) -> dict[str, object]:
    try:
        import ee
    except ImportError as exc:
        raise RuntimeError("MERIT sampling requires the 'earth-engine' extra") from exc
    import tomllib
    config = tomllib.loads((ROOT / "config" / "earth_engine.toml").read_text(encoding="utf-8"))
    started = time.perf_counter()
    ee.Initialize(project=config["project_id"])
    image = ee.Image(config["asset_id"])
    point = ee.Geometry.Point([float(row["Longitude"]), float(row["Latitude"])], proj="EPSG:4326")
    values = image.select(list(BANDS)).reduceRegion(reducer=ee.Reducer.first(), geometry=point,
        scale=config["sampling_scale_m"], crs=config["sampling_projection"], maxPixels=1000).getInfo()
    elapsed = time.perf_counter() - started
    metrics.source["earth_engine"]["requests"] += 1
    metrics.source["earth_engine"]["elapsed_s"] += elapsed
    LOG.info("source=earth_engine site=%s request=reduceRegion.getInfo elapsed_s=%.3f", row["sample_id"], elapsed)
    return {"project_id": config["project_id"], "dataset": config["asset_id"], "bands": list(BANDS),
            "sampling_scale_m": config["sampling_scale_m"], "values": {b: values.get(b) for b in BANDS},
            "classification": {b: "nodata_or_masked" if values.get(b) is None else "valid_value" for b in BANDS}}


def run(stage: int) -> dict[str, object]:
    if stage not in (5, 40): raise ValueError("stage must be exactly 5 or 40")
    selected = rows()[:stage]
    if len(selected) != stage: raise RuntimeError(f"expected {stage} sites, found {len(selected)}")
    metrics = Metrics(); results = []
    for row in selected:
        site_started = time.perf_counter(); LOG.info("site_start site=%s stage=%s", row["sample_id"], stage)
        metadata, array, dem = cache_dem(row, metrics)
        topo = extract_window(array, metadata, source_path=metadata.local_cached_path)
        merit_values = merit(row, metrics)
        catchment = delineate_catchment(float(row["Latitude"]), float(row["Longitude"]), ecotype=row["Ecotype"])
        results.append({"site": row, "topography": {"elevation_m": topo.elevation_m, "slope_degrees": topo.slope_degrees,
            "local_relief_m": topo.local_relief_m, "status": topo.status, "provenance": dem}, "merit_hydro": merit_values,
            "hydrology": {"status": catchment.status, "message": catchment.message}})
        elapsed = time.perf_counter() - site_started; metrics.site_timings.append({"sample_id": row["sample_id"], "wall_time_s": round(elapsed, 6)})
        LOG.info("site_done site=%s wall_time_s=%.3f", row["sample_id"], elapsed)
    if len({x["site"]["sample_id"] for x in results}) != stage: raise RuntimeError("duplicate/missing site IDs")
    for result in results:
        if result["topography"]["status"] not in {"ok", "no_valid_dem_data"}:
            raise RuntimeError(f"unexpected topography status for {result['site']['sample_id']}")
    runtime = metrics.finish()
    payload = {"status": "ok", "stage": f"{stage}_sites", "stage_size": stage, "run_id": str(uuid.uuid4()),
               "created_at_utc": datetime.now(timezone.utc).isoformat(), "results": results, "runtime": runtime,
               "validation": {"expected_rows": stage, "actual_rows": len(results), "ids_unique": True}}
    out = ROOT / "data" / "cache" / "staged_pilot" / f"stage_{stage}_sites.json"
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--stage", type=int, required=True, choices=(5, 40)); args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    payload = run(args.stage); print(json.dumps(payload, indent=2, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
