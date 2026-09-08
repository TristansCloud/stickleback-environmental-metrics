"""Run the guarded one-site end-to-end environmental pilot for S0002.

The guard is intentional: this command cannot run five or forty sites.  It
reads a 3x3 Copernicus GLO-30 COG window via HTTP range requests, caches only
that clipped GeoTIFF, and makes one Earth Engine reduceRegion call for MERIT.
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import ee
import rasterio
from rasterio.windows import Window

from enviro_data.dem_acquisition import RasterMetadata, retrieval_timestamp
from enviro_data.hydrology import delineate_catchment
from enviro_data.topography import extract_window

ROOT = Path(__file__).resolve().parents[1]
SITE_ID = "S0002"
COPERNICUS_BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
BANDS = ("elv", "dir", "upa", "upg", "hnd", "wat", "wth")


def site_row() -> dict[str, str]:
    with (ROOT / "pilot_sites_v1.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    matches = [row for row in rows if row["sample_id"] == SITE_ID]
    if len(matches) != 1:
        raise RuntimeError(f"stage one requires exactly one {SITE_ID} row")
    return matches[0]


def copernicus_url(latitude: float, longitude: float) -> str:
    lat, lon = int(latitude // 1), int(longitude // 1)
    ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
    stem = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
    return f"{COPERNICUS_BUCKET}/{stem}/{stem}.tif"


def cache_dem(row: dict[str, str]) -> tuple[RasterMetadata, object, dict[str, object]]:
    lat, lon = float(row["Latitude"]), float(row["Longitude"])
    url = copernicus_url(lat, lon)
    out = ROOT / "data" / "cache" / "stage_one_v2" / f"{SITE_ID}_copernicus_3x3.tif"
    meta_path = out.with_suffix(out.suffix + ".json")
    if out.is_file() and meta_path.is_file():
        metadata = RasterMetadata(**json.loads(meta_path.read_text(encoding="utf-8")))
        metadata.validate(out)
        with rasterio.open(out) as ds:
            values = ds.read(1)
        return metadata, values, {"status": "cache_hit", "path": str(out)}
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open("/vsicurl/" + url) as source:
        row_index, col_index = source.index(lon, lat)
        window = Window(max(0, col_index - 1), max(0, row_index - 1), 3, 3)
        values = source.read(1, window=window, boundless=True, masked=False)
        transform = source.window_transform(window)
        profile = source.profile.copy()
        profile.update(driver="GTiff", height=3, width=3, transform=transform, compress="deflate", nodata=-9999.0)
        values = values.astype("float32")
        if source.nodata is not None:
            values[values == source.nodata] = -9999.0
        with rasterio.open(out, "w", **profile) as target:
            target.write(values, 1)
        source_crs = str(source.crs)
        # GLO-30 is stored in geographic degrees but its advertised ground
        # sampling is 30 m; use metres for gradient calculations and record
        # the CRS separately.
        resolution = 30.0
    checksum = hashlib.sha256(out.read_bytes()).hexdigest()
    metadata = RasterMetadata(url, f"GLO30:{SITE_ID}", "Copernicus DEM AWS Open Data", retrieval_timestamp(), checksum,
                              source_crs, "EGM2008 (provider metadata)", resolution, str(out), nodata=-9999.0,
                              zero_is_ocean_nodata=False)
    metadata.validate(out)
    meta_path.write_text(json.dumps(metadata.__dict__ if hasattr(metadata, "__dict__") else {
        "source_url": metadata.source_url, "item_id": metadata.item_id, "provider": metadata.provider,
        "retrieval_date": metadata.retrieval_date, "checksum_sha256": metadata.checksum_sha256,
        "source_crs": metadata.source_crs, "vertical_datum": metadata.vertical_datum,
        "resolution_m": metadata.resolution_m, "local_cached_path": metadata.local_cached_path,
        "nodata": metadata.nodata, "zero_is_ocean_nodata": metadata.zero_is_ocean_nodata}, indent=2) + "\n", encoding="utf-8")
    return metadata, values, {"status": "acquired", "path": str(out), "window_shape": [3, 3], "remote_url": url}


def merit(row: dict[str, str]) -> dict[str, object]:
    config = tomllib.loads((ROOT / "config" / "earth_engine.toml").read_text(encoding="utf-8"))
    project, dataset = config["project_id"], config["asset_id"]
    ee.Initialize(project=project)
    image = ee.Image(dataset)
    point = ee.Geometry.Point([float(row["Longitude"]), float(row["Latitude"])], proj="EPSG:4326")
    values = image.select(list(BANDS)).reduceRegion(reducer=ee.Reducer.first(), geometry=point,
        scale=config["sampling_scale_m"], crs=config["sampling_projection"], maxPixels=1000).getInfo()
    return {"project_id": project, "dataset": dataset, "bands": list(BANDS),
            "sampling_scale_m": config["sampling_scale_m"], "values": {b: values.get(b) for b in BANDS},
            "classification": {b: "nodata_or_masked" if values.get(b) is None else "valid_value" for b in BANDS}}


def main() -> int:
    row = site_row()
    metadata, array, dem = cache_dem(row)
    topo = extract_window(array, metadata, source_path=metadata.local_cached_path)
    catchment = delineate_catchment(float(row["Latitude"]), float(row["Longitude"]), ecotype=row["Ecotype"])
    result = {"status": "ok", "stage": "one_site", "site": row, "topography": {
        "elevation_m": topo.elevation_m, "slope_degrees": topo.slope_degrees, "local_relief_m": topo.local_relief_m,
        "status": topo.status, "provenance": dem}, "merit_hydro": merit(row),
        "hydrology": {"status": "not_implemented_no_delineation", "catchment": {
            "status": catchment.status, "message": catchment.message}},
        "runtime": {"python": sys.version, "platform": platform.platform(), "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}}
    out = ROOT / "data" / "cache" / "stage_one_v2" / f"{SITE_ID}_processed.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
