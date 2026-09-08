"""Read one MERIT Hydro point through Earth Engine.

This is an explicitly bounded online smoke test: exactly S0002, no export,
no raster download, and no authentication flow. Existing Earth Engine
credentials are required (``ee.Initialize`` only).
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import ee


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "earth_engine.toml"
RESULT = ROOT / "data" / "cache" / "merit_hydro" / "S0002_earth_engine_smoke.json"
SITE = {"sample_id": "S0002", "latitude": 69.5856, "longitude": 27.5854, "ecotype": "freshwater"}
REQUIRED_BANDS = ("elv", "dir", "upa", "upg", "hnd", "wat", "wth")


def load_config() -> dict:
    with CONFIG.open("rb") as handle:
        return tomllib.load(handle)


def classify(value: object) -> str:
    # Do not convert null/masked cells to elevation zero. A numeric zero remains
    # an observed source value and is therefore classified as valid_value.
    return "nodata_or_masked" if value is None else "valid_value"


def main() -> int:
    config = load_config()
    project = config["project_id"]
    dataset = config["asset_id"]
    configured_bands = tuple(config["bands"])
    if set(configured_bands) != set(REQUIRED_BANDS) or len(configured_bands) != len(REQUIRED_BANDS):
        raise ValueError(f"configured bands must contain exactly {REQUIRED_BANDS}; got {configured_bands}")
    bands = REQUIRED_BANDS

    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result: dict[str, object] = {
        "status": "error",
        "scope": "exactly one freshwater pilot site; no export or raster download",
        "site": SITE,
        "source": {
            "provider": "Google Earth Engine",
            "dataset": dataset,
            "bands_requested": list(bands),
            "project_id": project,
            "sampling_scale_m": config["sampling_scale_m"],
            "sampling_projection": config["sampling_projection"],
            "sampling_reducer": config["sampling_reducer"],
        },
        "retrieved_at_utc": retrieved,
        "runtime": {"python": sys.version, "platform": platform.platform(), "ee_version": getattr(ee, "__version__", None)},
        "values": {},
        "classification": {},
        "network": {"authentication_called": False, "export_submitted": False, "raster_downloaded": False},
    }
    try:
        ee.Initialize(project=project)
        image = ee.Image(dataset)
        available = image.bandNames().getInfo()
        result["source"]["bands_available"] = available
        missing = [band for band in bands if band not in available]
        if missing:
            raise RuntimeError(f"dataset missing requested bands: {missing}")
        point = ee.Geometry.Point([SITE["longitude"], SITE["latitude"]], proj="EPSG:4326")
        sampled = image.select(list(bands)).reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=config["sampling_scale_m"],
            crs=config["sampling_projection"],
            maxPixels=1000,
        ).getInfo()
        values = {band: sampled.get(band) for band in bands}
        result["values"] = values
        result["classification"] = {band: classify(values[band]) for band in bands}
        result["status"] = "ok"
    except Exception as exc:  # preserve exact remote/client failure in the record
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}

    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
    result["provenance_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
