"""Run at most seven provisional river sites; cached/offline by default."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

from enviro_data.input import load_sites
from enviro_data.lake_lookup import CacheClient, OverpassUnavailable, atomic_json
from enviro_data.river_snapping import align_merit_cell, comparison_metrics, snap_stream
from enviro_data.river_sources import local_merit, merit_window, osm_streams, sha

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("enviro_data.river_pilot")


def run(
    source,
    output_dir,
    *,
    vectors=None,
    merit_rasters=None,
    ee_config=None,
    live_osm=False,
    live_merit=False,
    max_requests=7,
    max_failures=2,
    timeout=25,
    delay=2.0,
    max_distance=500.0,
    sample_id=None,
    max_sites=7,
):
    source, output_dir = Path(source), Path(output_dir)
    load_sites(source, strict=True)
    with source.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if (
        not 1 <= max_sites <= 100
        or not 1 <= len(rows) <= max_sites
        or any(r.get("pilot_class") != "stream" for r in rows)
    ):
        raise ValueError(
            "input must be a stream cohort within the explicit max_sites bound (up to 100)"
        )
    if sample_id:
        rows = [r for r in rows if r["sample_id"] == sample_id]
        if not rows:
            raise ValueError("sample_id not in pilot")
    if (
        not 1 <= max_requests <= 14
        or not 1 <= max_failures <= 7
        or not 0 < timeout <= 45
    ):
        raise ValueError("invalid request/failure/time bounds")
    if vectors and live_osm or merit_rasters and live_merit:
        raise ValueError("choose local or live source for each data type")
    identity = {
        "version": "river-snap-v1",
        "input_sha256": sha(source),
        "sample_ids": [r["sample_id"] for r in rows],
        "max_distance_m": max_distance,
        "vector_sha256": sha(vectors) if vectors else None,
        "merit_config_sha256": sha(merit_rasters) if merit_rasters else None,
        "ee_config_sha256": (
            sha(ee_config) if ee_config and Path(ee_config).exists() else None
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "selection_manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()) != identity:
        raise ValueError("output configuration differs; choose a new output directory")
    atomic_json(manifest, identity)
    local_features = None
    if vectors:
        payload = json.loads(Path(vectors).read_text())
        if payload.get("type") != "FeatureCollection" or payload.get("crs"):
            raise ValueError(
                "vectors must be RFC 7946 WGS84 GeoJSON without a legacy CRS"
            )
        local_features = payload["features"]
    client = CacheClient(
        output_dir / "osm_cache",
        live=live_osm,
        delay=delay,
        timeout=timeout,
        retries=0,
        max_requests=max_requests,
    )
    results, failures = [], 0
    for row in rows:
        site_id = row["sample_id"]
        LOG.info("site=%s stage=vector_start", site_id)
        vector_source, vector_error = {}, None
        try:
            if local_features is not None:
                features = local_features
                vector_source = {"source": str(vectors), "sha256": sha(vectors)}
            else:
                features, vector_source = osm_streams(
                    client,
                    float(row["Latitude"]),
                    float(row["Longitude"]),
                    max_distance,
                )
            snap = snap_stream(row, features, max_distance_m=max_distance)
            failures = 0
        except (OverpassUnavailable, OSError, ValueError) as error:
            vector_error = f"{type(error).__name__}: {error}"
            failures += 1
            snap = snap_stream(row, [], max_distance_m=max_distance)
            snap["status"] = (
                "vector_retrieval_failed" if live_osm else "vector_source_unavailable"
            )
            LOG.warning("site=%s stage=vector_failed error=%s", site_id, vector_error)
        LOG.info(
            "site=%s stage=vector_done status=%s candidates=%d",
            site_id,
            snap["status"],
            snap["candidate_count"],
        )
        original = (float(row["Longitude"]), float(row["Latitude"]))
        selected = snap["selected"]
        snapped = (selected["longitude"], selected["latitude"]) if selected else None
        raster_source, raster_error, raw = {}, None, {}
        alignment = {"status": "merit_unavailable", "selected": None, "candidates": []}
        try:
            if merit_rasters:
                window = local_merit(merit_rasters, original, snapped)
            else:
                window = merit_window(
                    original,
                    snapped,
                    output_dir / "merit_cache",
                    config=ee_config,
                    live=live_merit,
                )
            raw = window["original"]
            raster_source = window["source"]
            alignment = align_merit_cell(snap, window["cells"])
        except Exception as error:
            # A missing source/credential is a failure status, never a zero value.
            raster_error = f"{type(error).__name__}: {error}"
            LOG.warning("site=%s stage=merit_failed error=%s", site_id, raster_error)
        LOG.info("site=%s stage=merit_done status=%s", site_id, alignment["status"])
        props = selected["properties"] if selected else {}
        result = {
            "sample_id": site_id,
            "site": row,
            "snap": snap,
            "alignment": alignment,
            "original_merit_values": raw,
            "metrics": comparison_metrics(raw, alignment),
            "reach_attributes": {
                k: props.get(k)
                for k in (
                    "HYRIV_ID",
                    "NEXT_DOWN",
                    "ORD_STRA",
                    "UPLAND_SKM",
                    "DIS_AV_CMS",
                )
            },
            "reach_attribute_note": "HydroRIVERS upstream area is at reach outlet; these attributes are not sample-point measurements",
            "provenance": {"vector": vector_source, "merit": raster_source},
            "errors": {"vector": vector_error, "merit": raster_error},
            "classification_status": "provisional_unverified",
            "review_required": True,
        }
        atomic_json(output_dir / "checkpoints" / f"{site_id}.json", result)
        results.append(result)
        write_outputs(results, output_dir)
        if live_osm and (
            failures >= max_failures or client.request_count >= max_requests
        ):
            LOG.warning("stopping: vector failure limit or request budget reached")
            break
    metadata = {
        **identity,
        "processed": len(results),
        "unprocessed_ids": [r["sample_id"] for r in rows[len(results) :]],
        "osm_network_requests": client.request_count,
        "live_osm": live_osm,
        "live_merit": live_merit,
        "provisional_vector_matches": sum(
            r["snap"]["selected"] is not None for r in results
        ),
        "provisional_channel_cells": sum(
            r["alignment"]["selected"] is not None for r in results
        ),
        "metrics_complete": all(r["alignment"]["selected"] is not None for r in results)
        and len(results) == len(rows),
    }
    atomic_json(output_dir / "run_metadata.json", metadata)
    return metadata


def write_outputs(results, destination):
    flat, features = [], []
    for result in results:
        snap, alignment = result["snap"], result["alignment"]
        selected, cell = snap["selected"], alignment["selected"]
        row = {
            "sample_id": result["sample_id"],
            "population_name": result["site"]["Population.name"],
            "source_ecotype": result["site"]["Ecotype"],
            "validation_role": result["site"]["validation_role"],
            "original_longitude": snap["original_longitude"],
            "original_latitude": snap["original_latitude"],
            "vector_status": snap["status"],
            "reach_id": selected["reach_id"] if selected else None,
            "snap_distance_m": selected["distance_m"] if selected else None,
            "vector_longitude": selected["longitude"] if selected else None,
            "vector_latitude": selected["latitude"] if selected else None,
            "merit_status": alignment["status"],
            "cell_longitude": cell["longitude"] if cell else None,
            "cell_latitude": cell["latitude"] if cell else None,
            "cell_distance_from_vector_snap_m": (
                cell["distance_from_vector_snap_m"] if cell else None
            ),
            "review_required": True,
            "flow_connection_verified": False,
        }
        for name, metric in result["metrics"].items():
            for suffix, value in metric.items():
                row[f"{name}__{suffix}"] = value
        row["errors"] = json.dumps(result["errors"])
        flat.append(row)
        for role, coordinate in [
            ("original", [snap["original_longitude"], snap["original_latitude"]]),
            (
                "vector_snap",
                [selected["longitude"], selected["latitude"]] if selected else None,
            ),
            ("merit_cell", [cell["longitude"], cell["latitude"]] if cell else None),
        ]:
            if coordinate:
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": coordinate},
                        "properties": {
                            "sample_id": result["sample_id"],
                            "role": role,
                            "status": row["merit_status"],
                            "review_required": True,
                        },
                    }
                )
        for candidate in snap["candidates"]:
            features.append(
                {
                    "type": "Feature",
                    "geometry": candidate["geometry"],
                    "properties": {
                        "sample_id": result["sample_id"],
                        "role": "candidate_reach",
                        "reach_id": candidate["reach_id"],
                        "distance_m": candidate["distance_m"],
                        "name_evidence": candidate["name_evidence"],
                        "review_required": True,
                    },
                }
            )
    temp = destination / "river_pilot.csv.tmp"
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(flat)
    temp.replace(destination / "river_pilot.csv")
    atomic_json(
        destination / "river_pilot.geojson",
        {"type": "FeatureCollection", "features": features},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/habitat_pilots/stream_pilot_sites_v1.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "data/cache/river_pilot"
    )
    parser.add_argument(
        "--vectors", type=Path, help="Local RFC 7946 OSM/HydroRIVERS GeoJSON"
    )
    parser.add_argument(
        "--merit-rasters", type=Path, help="JSON mapping of six local MERIT bands"
    )
    parser.add_argument(
        "--ee-config", type=Path, default=ROOT / "config/earth_engine.toml"
    )
    parser.add_argument("--live-osm", action="store_true")
    parser.add_argument("--live-merit", action="store_true")
    parser.add_argument("--max-requests", type=int, default=7)
    parser.add_argument("--max-failures", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--delay", type=float, default=2)
    parser.add_argument("--max-distance", type=float, default=500)
    parser.add_argument("--sample-id")
    parser.add_argument("--max-sites", type=int, default=7)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    metadata = run(
        args.input,
        args.output_dir,
        vectors=args.vectors,
        merit_rasters=args.merit_rasters,
        ee_config=args.ee_config,
        live_osm=args.live_osm,
        live_merit=args.live_merit,
        max_requests=args.max_requests,
        max_failures=args.max_failures,
        timeout=args.timeout,
        delay=args.delay,
        max_distance=args.max_distance,
        sample_id=args.sample_id,
        max_sites=args.max_sites,
    )
    print(json.dumps(metadata, indent=2))
    return 0 if metadata["metrics_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
