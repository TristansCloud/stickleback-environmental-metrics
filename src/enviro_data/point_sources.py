"""Cache-first public point elevation and atmospheric climatology adapters."""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request

from .osm_http import bounded_urlopen
from .river_snapping import number

MONTHS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


def fetch_json(url, cache_dir, *, live=False, timeout=25):
    path = Path(cache_dir) / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.exists():
        envelope = json.loads(path.read_text())
        if envelope.get("url") != url:
            raise ValueError("cache URL mismatch")
        return envelope["payload"], {
            "cache": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "retrieved_at_utc": envelope["retrieved_at_utc"],
            "url": url,
        }
    if not live:
        raise RuntimeError("cache_missing_live_disabled")
    with bounded_urlopen(
        Request(
            url,
            headers={
                "User-Agent": "stickleback-environmental-metrics/0.1 (research point pilot)"
            },
        ),
        timeout=timeout,
    ) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError("response exceeds 8 MB")
    payload = json.loads(raw)
    if payload.get("error") or payload.get("messages") and "properties" not in payload:
        raise ValueError(f"API error: {payload}")
    envelope = {
        "url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, indent=2) + "\n")
    return payload, {
        "cache": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "retrieved_at_utc": envelope["retrieved_at_utc"],
        "url": url,
    }


def elevation_batch(coordinates, cache_dir, *, live=False):
    if not 1 <= len(coordinates) <= 100:
        raise ValueError("elevation accepts 1 to 100 points")
    query = urlencode(
        {
            "latitude": ",".join(str(p[1]) for p in coordinates),
            "longitude": ",".join(str(p[0]) for p in coordinates),
        }
    )
    payload, provenance = fetch_json(
        "https://api.open-meteo.com/v1/elevation?" + query, cache_dir, live=live
    )
    values = payload.get("elevation")
    if not isinstance(values, list) or len(values) != len(coordinates):
        raise ValueError("elevation response length mismatch")
    return [number(v) for v in values], {
        **provenance,
        "source": "Open-Meteo / Copernicus DEM GLO-90 2021",
        "resolution_m": 90,
        "unit": "m",
        "method": "original coordinate DEM sample; not bathymetry or measured lake surface",
    }


def climate_point(lon, lat, cache_dir, *, live=False):
    query = urlencode(
        {
            "parameters": "T2M,PRECTOTCORR",
            "community": "AG",
            "longitude": lon,
            "latitude": lat,
            "format": "JSON",
        }
    )
    payload, provenance = fetch_json(
        "https://power.larc.nasa.gov/api/temporal/climatology/point?" + query,
        cache_dir,
        live=live,
    )
    return parse_climate(payload), {
        **provenance,
        "source": "NASA POWER / MERRA-2 atmospheric climatology",
        "period": payload.get("header", {}).get("range"),
        "api": payload.get("header", {}).get("api"),
        "parameters": payload.get("parameters"),
        "provider_coordinates": payload.get("geometry", {}).get("coordinates"),
        "method": "source native coarse grid; atmospheric context, not aquatic temperature",
    }


def parse_climate(payload):
    metadata = payload.get("parameters", {})
    if (
        metadata.get("T2M", {}).get("units") not in {"C", "degC"}
        or metadata.get("PRECTOTCORR", {}).get("units") != "mm/day"
    ):
        raise ValueError("unexpected climate units")
    fill = payload.get("header", {}).get("fill_value", -999)
    parameters = payload.get("properties", {}).get("parameter", {})

    def value(parameter, month):
        result = number(parameters.get(parameter, {}).get(month))
        if (
            result == fill
            or parameter == "PRECTOTCORR"
            and result is not None
            and result < 0
        ):
            return None
        return result

    temperatures = [value("T2M", m) for m in MONTHS]
    rain = [value("PRECTOTCORR", m) for m in MONTHS]
    result = {
        "climate_period": payload.get("header", {}).get("range"),
        "mean_annual_air_temperature_c": value("T2M", "ANN"),
        "annual_mean_precipitation_mm_day": value("PRECTOTCORR", "ANN"),
        "warmest_month_mean_air_temperature_c": (
            max(temperatures) if all(v is not None for v in temperatures) else None
        ),
        "coldest_month_mean_air_temperature_c": (
            min(temperatures) if all(v is not None for v in temperatures) else None
        ),
        "monthly_mean_air_temperature_range_c": (
            max(temperatures) - min(temperatures)
            if all(v is not None for v in temperatures)
            else None
        ),
    }
    for month, temperature, precipitation in zip(MONTHS, temperatures, rain):
        result[f"air_temperature_{month.lower()}_c"] = temperature
        result[f"precipitation_{month.lower()}_mm_day"] = precipitation
    result["climate_status"] = (
        "ok"
        if all(v is not None for v in temperatures + rain)
        else "partial_or_missing"
    )
    return result
