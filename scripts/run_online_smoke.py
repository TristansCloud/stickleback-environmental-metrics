"""Bounded online smoke checks for one freshwater pilot site.

This is deliberately not a data-acquisition run.  It reads the first freshwater
pilot coordinate, requests only the first 4096 bytes of its public Copernicus
GLO-30 COG, and checks whether the local Earth Engine Python client/credentials
are already available.  It never calls ``ee.Authenticate`` and never submits an
Earth Engine request.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import platform
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "pilot_sites_v1.csv"
REPORT = ROOT / "docs" / "online_smoke_test_2026-09-07.json"
CACHE = ROOT / "data" / "cache" / "online_smoke"
COPERNICUS_BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
RANGE_BYTES = 4096


def first_freshwater() -> dict[str, str]:
    with PILOT.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["Ecotype"].strip().lower() == "freshwater":
                return row
    raise RuntimeError("pilot contains no freshwater site")


def copernicus_url(latitude: float, longitude: float) -> str:
    # GLO-30 public COG mirror uses one-degree tile names with the southwest
    # integer corner, e.g. N69_00_E027_00 for 69.5856 N, 27.5854 E.
    lat = int(latitude // 1)
    lon = int(longitude // 1)
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    stem = f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"
    return f"{COPERNICUS_BUCKET}/{stem}/{stem}.tif"


def range_read(url: str) -> tuple[bytes, dict[str, str], int]:
    request = urllib.request.Request(
        url,
        headers={"Range": f"bytes=0-{RANGE_BYTES - 1}", "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read(RANGE_BYTES)
        return body, dict(response.headers.items()), response.status


def earth_engine_preflight() -> dict[str, object]:
    ee_config = ROOT / "config" / "earth_engine.toml"
    project_id = "stickleback-507923"
    if ee_config.is_file():
        try:
            import tomllib

            project_id = tomllib.loads(ee_config.read_text(encoding="utf-8")).get(
                "project_id", project_id
            )
        except Exception:
            pass
    module_available = importlib.util.find_spec("ee") is not None
    credential_candidates = [
        Path.home() / ".config" / "earthengine",
        Path(os.environ.get("APPDATA", "")) / "earthengine",
    ]
    credential_paths = [str(p) for p in credential_candidates if p.is_file() or p.is_dir()]
    return {
        "project_id": project_id,
        "python_module_available": module_available,
        "credential_locations_detected": credential_paths,
        "authenticated_read_attempted": False,
        "status": "ready_for_authentication"
        if module_available and credential_paths
        else "not_ready_no_local_earth_engine_credentials",
        "setup_command": (
            "python -m pip install earthengine-api && "
            "python -c \"import ee; ee.Authenticate(); "
            f"ee.Initialize(project='{project_id}')\""
        ),
    }


def main() -> int:
    site = first_freshwater()
    url = copernicus_url(float(site["Latitude"]), float(site["Longitude"]))
    result: dict[str, object] = {
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "scope": "one freshwater pilot site; no full-dataset run",
        "site": {key: site[key] for key in ("sample_id", "Latitude", "Longitude", "Ecotype")},
        "copernicus": {"url": url, "requested_range": "bytes=0-4095", "max_bytes": RANGE_BYTES},
        "earth_engine": earth_engine_preflight(),
        "runtime": {"python": sys.version, "platform": platform.platform()},
    }
    try:
        body, headers, status = range_read(url)
        cached = CACHE / f"{site['sample_id']}_copernicus_header_4k.bin"
        CACHE.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(body)
        result["copernicus"].update(
            {
                "status": "ok" if status == 206 and body[:4] in (b"II*\x00", b"MM\x00*" ) else "unexpected_response",
                "http_status": status,
                "bytes_received": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "content_range": headers.get("Content-Range"),
                "content_length": headers.get("Content-Length"),
                "etag": headers.get("ETag"),
                "content_type": headers.get("Content-Type"),
                "local_cached_path": str(cached),
                "is_tiff_signature": body[:4] in (b"II*\x00", b"MM\x00*"),
                "full_raster_downloaded": False,
            }
        )
    except Exception as exc:  # report network failure without retrying/broadening scope
        result["copernicus"].update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
    REPORT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["copernicus"]["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
