"""Cached OSM channels and bounded local/Earth Engine MERIT windows."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from .lake_lookup import CacheClient
from .river_snapping import BANDS, number

DATASET = "MERIT/Hydro/v1_0_1"
MAX_CELLS = 400
WINDOW_RADIUS_M = 200


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def osm_streams(client: CacheClient, lat, lon, radius=500):
    if not 0 < radius <= 500:
        raise ValueError("OSM radius must be within 500 m")
    query = (
        f"[out:json][timeout:20];way(around:{radius},{lat},{lon})"
        '[waterway~"^(river|stream)$"];out body geom;'
    )
    payload, retrieval, cache = client._fetch(
        client.endpoint, urlencode({"data": query}).encode(), stage="river_vectors"
    )
    features = []
    for element in payload["elements"]:
        geometry = element.get("geometry") or []
        if element.get("type") != "way" or len(geometry) < 2:
            continue
        features.append(
            {
                "type": "Feature",
                "id": f"way/{element['id']}",
                "properties": element.get("tags", {}),
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[p["lon"], p["lat"]] for p in geometry],
                },
            }
        )
    return features, {
        "source": "OpenStreetMap",
        "retrieval": retrieval,
        "cache": str(cache),
        "sha256": sha(cache),
        "query": query,
        "snapshot": payload.get("osm3s", {}).get("timestamp_osm_base"),
    }


def local_merit(config_path, original, snapped):
    """Read six aligned, native EPSG:4326 MERIT rasters, at most 400 cells."""
    import rasterio
    from contextlib import ExitStack
    from rasterio.windows import Window

    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    if config.get("dataset") != DATASET:
        raise ValueError("local raster configuration must identify MERIT/Hydro/v1_0_1")
    with ExitStack() as stack:
        rasters, sources = {}, {}
        for band in BANDS:
            path = config_path.parent / config["bands"][band]
            rasters[band] = stack.enter_context(rasterio.open(path))
            sources[band] = {"path": str(path), "sha256": sha(path)}
        base = rasters["upa"]
        transform = base.transform
        if (
            base.crs != rasterio.crs.CRS.from_epsg(4326)
            or transform.b != 0
            or transform.d != 0
        ):
            raise ValueError("local MERIT requires north-up EPSG:4326 native rasters")
        if not math.isclose(transform.a, 1 / 1200, abs_tol=1e-9) or not math.isclose(
            transform.e, -1 / 1200, abs_tol=1e-9
        ):
            raise ValueError("local MERIT must retain native 3 arc-second grid")
        if any(
            ds.crs != base.crs or ds.transform != transform or ds.shape != base.shape
            for ds in rasters.values()
        ):
            raise ValueError("MERIT bands have inconsistent grids")

        def cell_values(row, col):
            if not 0 <= row < base.height or not 0 <= col < base.width:
                return dict.fromkeys(BANDS)
            values = {}
            for band, ds in rasters.items():
                value = ds.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
                values[band] = (
                    None if bool(getattr(value, "mask", False)) else number(value)
                )
            return values

        row, col = base.index(*original)
        raw = cell_values(row, col)
        cells = []
        if snapped:
            lon, lat = snapped
            dx = WINDOW_RADIUS_M / (111195 * math.cos(math.radians(lat)))
            dy = WINDOW_RADIUS_M / 111195
            top, left = base.index(lon - dx, lat + dy)
            bottom, right = base.index(lon + dx, lat - dy)
            if (bottom - top + 1) * (right - left + 1) > MAX_CELLS:
                raise ValueError("native MERIT window exceeds 400 cells")
            for row in range(max(0, top), min(base.height, bottom + 1)):
                for col in range(max(0, left), min(base.width, right + 1)):
                    x, y = base.xy(row, col)
                    cells.append(
                        {"longitude": x, "latitude": y, "values": cell_values(row, col)}
                    )
        return {
            "original": raw,
            "cells": cells,
            "source": {
                "dataset": DATASET,
                "method": "native_grid_local_rasters",
                "crs": str(base.crs),
                "transform": list(transform),
                "rasters": sources,
                "config_sha256": sha(config_path),
            },
        }


def merit_window(original, snapped, cache_dir, *, config=None, live=False, timeout=45):
    """A worker gives all Earth Engine initialization/requests a hard deadline."""
    identity = {
        "dataset": DATASET,
        "original": original,
        "snapped": snapped,
        "radius_m": WINDOW_RADIUS_M,
        "max_cells": MAX_CELLS,
        "version": 1,
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = Path(cache_dir) / f"{key}.json"
    if cache.exists():
        envelope = json.loads(cache.read_text())
        if envelope["request"] != json.loads(json.dumps(identity)):
            raise ValueError("MERIT cache identity mismatch")
        payload = envelope["result"]
    else:
        if not live:
            raise RuntimeError("merit_cache_missing_live_disabled")
        if not config or not Path(config).is_file():
            raise RuntimeError(
                "Earth Engine config missing; copy config/earth_engine.toml.example and set your project"
            )
        request = {**identity, "config": str(Path(config).resolve())}
        worker = subprocess.run(
            [sys.executable, "-m", "enviro_data.river_sources", "--ee-worker"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if worker.returncode:
            raise RuntimeError(
                f"earth_engine_worker_exit_{worker.returncode}: {worker.stderr[-1000:]}"
            )
        payload = json.loads(worker.stdout)
        if payload.get("error"):
            raise RuntimeError(payload["error"])
    if (
        not isinstance(payload.get("original"), dict)
        or not isinstance(payload.get("cells"), list)
        or len(payload["cells"]) > MAX_CELLS
    ):
        raise ValueError("invalid or oversized MERIT response")
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"request": identity, "result": payload}, indent=2) + "\n"
        )
        temporary.replace(cache)
    payload = dict(payload)
    payload["source"] = {
        **payload["source"],
        "cache": str(cache),
        "cache_sha256": sha(cache),
    }
    return payload


def ee_worker(request):
    try:
        import ee

        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        config = tomllib.loads(Path(request["config"]).read_text())
        if config.get("asset_id") != DATASET:
            raise ValueError("Earth Engine config must use MERIT/Hydro/v1_0_1")
        ee.Initialize(project=config["project_id"])
        image = ee.Image(DATASET).select(list(BANDS))
        projection = image.select("upa").projection()
        info = projection.getInfo()
        original = ee.Geometry.Point(request["original"])
        raw = image.reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=original,
            crs=info["crs"],
            crsTransform=info["transform"],
            maxPixels=4,
        ).getInfo()
        cells = []
        if request["snapped"]:
            region = ee.Geometry.Point(request["snapped"]).buffer(request["radius_m"])
            collection = (
                image.sample(
                    region=region,
                    projection=projection,
                    geometries=True,
                    dropNulls=False,
                )
                .limit(MAX_CELLS + 1)
                .getInfo()
            )
            if len(collection["features"]) > MAX_CELLS:
                raise ValueError("native MERIT window exceeds 400 cells")
            cells = [
                {
                    "longitude": f["geometry"]["coordinates"][0],
                    "latitude": f["geometry"]["coordinates"][1],
                    "values": {b: f["properties"].get(b) for b in BANDS},
                }
                for f in collection["features"]
            ]
        return {
            "original": {b: raw.get(b) for b in BANDS},
            "cells": cells,
            "source": {
                "dataset": DATASET,
                "method": "Earth Engine native projection; first at original point, native cell centres near vector snap",
                "projection": info,
                "project_id": config["project_id"],
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "ee_version": ee.__version__,
            },
        }
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"}


if __name__ == "__main__" and sys.argv[1:] == ["--ee-worker"]:
    print(json.dumps(ee_worker(json.load(sys.stdin))))
