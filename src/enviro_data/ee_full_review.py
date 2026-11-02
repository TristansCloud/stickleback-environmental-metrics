"""Prepare a checksum-verified, immutable full-review Earth Engine release offline."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

from .ee_app_assets import _canonical, _primitive, _sha256

SCHEMA = "ee_full_review_v1"
NUMERIC_SUFFIXES = ("_m", "_m2", "_km2", "_c", "_mm_day", "_m3_s", "_degrees", "_count", "_pixels", "_latitude", "_longitude")
NUMERIC_FIELDS = {"latitude", "longitude", "lake_shoreline_development", "river_reach_strahler_order"}
BOOLEAN_FIELDS = {"manual_review", "review_required", "river_flow_connection_verified"}


def scalar(key: str, value: str):
    if value == "":
        return None
    if key in BOOLEAN_FIELDS:
        if value not in ("True", "False", "true", "false"):
            raise ValueError(f"Invalid boolean {key}: {value}")
        return value.lower() == "true"
    if key in NUMERIC_FIELDS or key.endswith(NUMERIC_SUFFIXES):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"Non-finite measurement {key}")
        return result
    # IDs and names remain strings, even if they look numeric.
    return value


def prepare_full_review(bundle: Path, output_root: Path, expected_sites: int = 599) -> Path:
    manifest_path = bundle / "bundle_manifest.json"
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"original_sites.csv", "stickleback_full_review_v1.csv", "sample_points.geojson",
                "lake_candidates.geojson", "river_candidates.geojson", "source_provenance.json",
                "coverage_summary.json", "data_dictionary.csv"}
    checksums = source_manifest["files"]
    if not required <= checksums.keys():
        raise ValueError("Review manifest lacks required files")
    for name, checksum in checksums.items():
        if Path(name).name != name or _sha256(bundle / name) != checksum:
            raise ValueError(f"Source checksum mismatch or unsafe filename: {name}")
    source_digest = _sha256(manifest_path)
    release = SCHEMA + "_" + hashlib.sha256(_canonical({"source_manifest_sha256": source_digest, "schema": SCHEMA})).hexdigest()[:16]

    def rows(name):
        with (bundle / name).open(encoding="utf-8-sig", newline="") as handle:
            result = list(csv.DictReader(handle))
        ids = [r["sample_id"] for r in result]
        if len(result) != expected_sites or not all(ids) or len(set(ids)) != len(ids):
            raise ValueError(f"Expected {expected_sites} unique original sites: {name}")
        return {r["sample_id"]: r for r in result}

    original, table = rows("original_sites.csv"), rows("stickleback_full_review_v1.csv")
    if original.keys() != table.keys():
        raise ValueError("Review IDs differ from original sites")
    points = json.loads((bundle / "sample_points.geojson").read_text())["features"]
    if len(points) != expected_sites or {f["properties"]["sample_id"] for f in points} != original.keys():
        raise ValueError("Point collection IDs differ from original sites")
    provenance = json.loads((bundle / "source_provenance.json").read_text())
    features = []
    for point in sorted(points, key=lambda f: f["properties"]["sample_id"]):
        sample = point["properties"]["sample_id"]
        row, source = table[sample], original[sample]
        coords = [float(source["Longitude"]), float(source["Latitude"])]
        if (point["geometry"] != {"type": "Point", "coordinates": coords}
                or [float(row["longitude"]), float(row["latitude"])] != coords
                or row["source_ecotype"] != source["Ecotype"]):
            raise ValueError(f"Original coordinates/ecotype changed: {sample}")
        props = {key: scalar(key, value) for key, value in row.items()}
        props.update(app_release_id=release, source_bundle_sha256=source_digest,
                     has_lake_polygon=props.get("lake_area_m2") is not None,
                     has_river_attributes=props.get("river_reach_upstream_area_km2") is not None,
                     has_shoreline_profile=props.get("shoreline_elevation_status") == "exploratory")
        for family, source_key in (("point_elevation", "point_elevation_source_key"), ("climate", "climate_source_key")):
            key = row.get(source_key)
            props[family + "_provenance_json"] = _primitive(provenance.get("point_sources", {}).get(key))
        shore = provenance.get("shoreline_results", {}).get(sample, {})
        props["shoreline_sources_json"] = _primitive(shore.get("sources"))
        features.append({"type": "Feature", "geometry": copy.deepcopy(point["geometry"]), "properties": props})
    collections = {"sites": features}
    for name in ("lake_candidates", "river_candidates"):
        evidence = json.loads((bundle / (name + ".geojson")).read_text())["features"]
        converted = []
        for item in evidence:
            item = copy.deepcopy(item)
            if item["properties"]["sample_id"] not in original:
                raise ValueError(f"Unknown evidence sample in {name}")
            item["properties"] = {key: _primitive(value) for key, value in item["properties"].items()}
            item["properties"].update(app_release_id=release)
            converted.append(item)
        collections[name] = converted
    shoreline_points = []
    for sample, record in sorted(provenance.get("shoreline_results", {}).items()):
        if sample not in original:
            raise ValueError("Unknown shoreline evidence sample")
        groups = record.get("plan", {}).get("groups", {})
        elevations = record.get("sample_elevations_m", [])
        if sum(len(v) for v in groups.values()) != len(elevations):
            raise ValueError(f"Shoreline coordinate/elevation count mismatch: {sample}")
        # The collector flattened these groups in insertion order. Do not sort
        # them: the source JSON preserves that order alongside elevation values.
        offset = 0
        for group, coordinates in groups.items():
            for i, coord in enumerate(coordinates):
                value = elevations[offset]
                offset += 1
                shoreline_points.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": coord},
                    "properties": {"sample_id": sample, "app_release_id": release,
                        "group": group, "sample_index_in_group": i, "elevation_m": value,
                        "profile_status": record.get("status"), "source_resolution_m": 90,
                        "notice": "Sampling location; nearest native DSM cell, not an independent observation"}})
    collections["shoreline_samples"] = shoreline_points
    contents = {name + ".geojson": _canonical({"type": "FeatureCollection", "features": values})
                for name, values in collections.items()}
    manifest = {"schema_version": SCHEMA, "app_release_id": release,
                "source_manifest_sha256": source_digest, "source_manifest": source_manifest,
                "counts": {name: len(values) for name, values in collections.items()},
                "coverage": json.loads((bundle / "coverage_summary.json").read_text()),
                "collection_checksums": {name: hashlib.sha256(body).hexdigest() for name, body in contents.items()},
                "notice": "Frozen provisional evidence; no new environmental measurements. Display rounding only."}
    contents["manifest.json"] = _canonical(manifest)
    target = output_root / release
    if target.exists():
        if any(not (target / name).is_file() or (target / name).read_bytes() != body
               for name, body in contents.items()):
            raise ValueError("Existing immutable full-review release differs")
        return target
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".full-review-", dir=output_root))
    try:
        for name, body in contents.items():
            (staging / name).write_bytes(body)
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target
