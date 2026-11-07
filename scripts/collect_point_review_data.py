"""Collect point data in bounded batches, from pilots to the full source."""

from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from enviro_data.input import load_sites
from enviro_data.lake_lookup import atomic_json
from enviro_data.point_sources import climate_point, elevation_batch

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("point_review")


def run(source, output_dir, *, live=False, max_sites=30, climate_workers=2):
    records = load_sites(source, strict=True).records
    if not 1 <= max_sites <= 599 or not 1 <= climate_workers <= 2:
        raise ValueError("bounded at 599 sites and two climate workers")
    records = records[:max_sites]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results, provenance, failures = {}, {}, []
    snapshot = output_dir / "point_data.json"
    if snapshot.exists():
        previous = json.loads(snapshot.read_text())
        results, provenance = previous.get("sites", {}), previous.get("sources", {})

    for record in records:
        cached = results.get(record.sample_id)
        if cached and (
            cached.get("latitude") != record.latitude
            or cached.get("longitude") != record.longitude
        ):
            raise ValueError(
                f"coordinates changed for {record.sample_id}; use a new output directory"
            )

    def checkpoint():
        atomic_json(
            snapshot, {"sites": results, "sources": provenance, "errors": failures}
        )

    elevation_pending = [
        r
        for r in records
        if results.get(r.sample_id, {}).get("point_elevation_status") != "ok"
    ]
    for start in range(0, len(elevation_pending), 100):
        batch = elevation_pending[start : start + 100]
        try:
            values, source_info = elevation_batch(
                [(r.longitude, r.latitude) for r in batch],
                output_dir / "elevation_cache",
                live=live,
            )
            key = source_info["sha256"]
            provenance[key] = source_info
            for record, value in zip(batch, values):
                site = results.setdefault(record.sample_id, {})
                site.update(
                    latitude=record.latitude,
                    longitude=record.longitude,
                    point_elevation_m=value,
                    point_elevation_status=(
                        "ok" if value is not None else "no_valid_data"
                    ),
                    elevation_source_key=key,
                )
            LOG.info("elevation batch complete points=%d", len(batch))
        except Exception as error:
            failures.append(
                {"stage": "elevation", "error": f"{type(error).__name__}: {error}"}
            )
            LOG.warning("elevation failed: %s", error)
            break
        checkpoint()
        if live:
            time.sleep(1)

    # NASA advises one request per native meteorological cell. Preserve the
    # original point coordinates, while sharing its coarse atmospheric context.
    def grid(record):
        return (
            round(record.longitude / 0.625) * 0.625,
            round(record.latitude / 0.5) * 0.5,
        )

    groups = {}
    for record in records:
        groups.setdefault(grid(record), []).append(record)
    pending = []
    climate_fields = lambda value: {
        k: v
        for k, v in value.items()
        if k.startswith(("air_temperature_", "precipitation_", "climate_"))
        or k
        in {
            "mean_annual_air_temperature_c",
            "annual_mean_precipitation_mm_day",
            "warmest_month_mean_air_temperature_c",
            "coldest_month_mean_air_temperature_c",
            "monthly_mean_air_temperature_range_c",
        }
    }

    def apply_group(coordinate, members, data, key, representative):
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(provenance[key]["url"]).query)
        query_lon = float(query["longitude"][0])
        query_lat = float(query["latitude"][0])
        representative = (
            "nominal_grid_center"
            if (query_lon, query_lat) == coordinate
            else "original_point_query_in_same_nominal_cell"
        )
        for record in members:
            results.setdefault(record.sample_id, {}).update(
                latitude=record.latitude,
                longitude=record.longitude,
                **data,
                climate_source_key=key,
                climate_query_longitude=query_lon,
                climate_query_latitude=query_lat,
                climate_grid_longitude=coordinate[0],
                climate_grid_latitude=coordinate[1],
                climate_representative_sample_id=representative,
                climate_sampling_method="nearest nominal MERRA-2 0.5 latitude x 0.625 longitude grid cell; one representative query",
            )

    for coordinate, members in groups.items():
        cached = [
            r
            for r in members
            if results.get(r.sample_id, {}).get("climate_status") == "ok"
        ]
        if cached:
            first = cached[0]
            data = climate_fields(results[first.sample_id])
            for other in cached[1:]:
                other_data = climate_fields(results[other.sample_id])
                numeric = [
                    k
                    for k in data
                    if k.startswith(("air_temperature_", "precipitation_"))
                ]
                if any(data.get(k) != other_data.get(k) for k in numeric):
                    raise ValueError(
                        "climate values differ within nominal cell; do not share them"
                    )
            # Drop helper fields before merging keyword arguments.
            data = {
                k: v
                for k, v in data.items()
                if k
                not in {
                    "climate_source_key",
                    "climate_grid_longitude",
                    "climate_grid_latitude",
                    "climate_representative_sample_id",
                    "climate_sampling_method",
                    "climate_error",
                    "climate_query_longitude",
                    "climate_query_latitude",
                }
            }
            apply_group(
                coordinate,
                members,
                data,
                results[first.sample_id]["climate_source_key"],
                first.sample_id,
            )
        else:
            pending.append((coordinate, members))
    checkpoint()
    consecutive = 0

    def collect(item):
        coordinate, members = item
        data, source_info = climate_point(
            *coordinate, output_dir / "climate_cache", live=live
        )
        if live:
            time.sleep(1)
        return coordinate, members, data, source_info

    with ThreadPoolExecutor(max_workers=climate_workers) as executor:
        for start in range(0, len(pending), climate_workers):
            jobs = {
                executor.submit(collect, item): item
                for item in pending[start : start + climate_workers]
            }
            for future in as_completed(jobs):
                coordinate, members = jobs[future]
                try:
                    _, _, data, source_info = future.result()
                    known_periods = {
                        p["period"] for p in provenance.values() if p.get("period")
                    }
                    if known_periods and source_info["period"] not in known_periods:
                        raise ValueError(
                            "provider climatology period changed; use a separate run"
                        )
                    key = source_info["sha256"]
                    provenance[key] = source_info
                    apply_group(coordinate, members, data, key, "nominal_grid_center")
                    consecutive = 0
                    LOG.info(
                        "climate grid=%s complete sites=%d/%d",
                        coordinate,
                        sum(
                            results.get(r.sample_id, {}).get("climate_status") == "ok"
                            for r in records
                        ),
                        len(records),
                    )
                except Exception as error:
                    consecutive += 1
                    for record in members:
                        failures.append(
                            {
                                "sample_id": record.sample_id,
                                "stage": "climate",
                                "error": f"{type(error).__name__}: {error}",
                            }
                        )
                        results.setdefault(record.sample_id, {}).update(
                            latitude=record.latitude,
                            longitude=record.longitude,
                            climate_status="retrieval_failed",
                            climate_error=str(error),
                        )
                    LOG.warning("climate grid=%s failed: %s", coordinate, error)
                checkpoint()
            if consecutive >= 3:
                LOG.error("stopped after repeated climate failures")
                break
    checkpoint()
    return {
        "selected": len(records),
        "elevation_ok": sum(
            results.get(r.sample_id, {}).get("point_elevation_status") == "ok"
            for r in records
        ),
        "climate_ok": sum(
            results.get(r.sample_id, {}).get("climate_status") == "ok" for r in records
        ),
        "errors": len(failures),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ROOT / "site_overview_v1_clean.csv")
    p.add_argument("--output-dir", type=Path, default=ROOT / "data/cache/point_review")
    p.add_argument("--max-sites", type=int, default=30)
    p.add_argument("--live", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(
        json.dumps(
            run(args.input, args.output_dir, live=args.live, max_sites=args.max_sites),
            indent=2,
        )
    )
