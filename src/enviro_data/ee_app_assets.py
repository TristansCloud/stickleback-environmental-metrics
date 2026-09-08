"""Build offline-only, review-ready inputs for a future Earth Engine App.

This module deliberately has no Earth Engine or HTTP dependency.  It converts
the *frozen* staged pilot result, OSM matching table, cached Overpass payloads,
and cached Copernicus windows into portable GeoJSON/CSV artifacts.  It does not
upload assets, initialise Earth Engine, or alter any source/cache input.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "ee_app_validation_assets_v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON input: {path}") from exc


def _primitive(value: Any) -> Any:
    """Keep GeoJSON properties scalar, preserving null rather than inventing 0."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _flatten(prefix: str, value: Mapping[str, Any], into: dict[str, Any]) -> None:
    for key, item in sorted(value.items()):
        name = f"{prefix}_{key}" if prefix else key
        if isinstance(item, Mapping):
            _flatten(name, item, into)
        else:
            into[name] = _primitive(item)


def _read_matches(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "sample_id" not in rows[0]:
        raise ValueError(f"OSM match CSV lacks sample_id rows: {path}")
    matches = {row["sample_id"]: row for row in rows}
    if len(matches) != len(rows):
        raise ValueError("OSM match CSV has duplicate sample_id values")
    return matches


def _overpass_geometry(element: Mapping[str, Any]) -> dict[str, Any] | None:
    points = element.get("geometry")
    if not isinstance(points, list) or not points:
        return None
    try:
        coordinates = [[float(point["lon"]), float(point["lat"])] for point in points]
    except (KeyError, TypeError, ValueError):
        return None
    # Mirrors the matching adapter's representation exactly.
    polygon = len(coordinates) >= 3 and coordinates[0] == coordinates[-1]
    return {"type": "Polygon", "coordinates": [coordinates]} if polygon else {"type": "LineString", "coordinates": coordinates}


def _raw_osm_index(raw_dir: Path) -> tuple[dict[tuple[str, str], tuple[dict[str, Any], Path, dict[str, Any]]], list[dict[str, str]]]:
    index: dict[tuple[str, str], tuple[dict[str, Any], Path, dict[str, Any]]] = {}
    checksums: list[dict[str, str]] = []
    for path in sorted(raw_dir.glob("*.json")):
        payload = _load_json(path)
        if not isinstance(payload, Mapping):
            raise ValueError(f"raw OSM payload is not an object: {path}")
        checksums.append({"path": str(path.resolve()), "sha256": _sha256(path)})
        for element in payload.get("elements", []):
            if not isinstance(element, Mapping) or "type" not in element or "id" not in element:
                continue
            key = (str(element["type"]), str(element["id"]))
            if key in index and _canonical(index[key][0]) != _canonical(dict(element)):
                raise ValueError(f"conflicting cached geometries for OSM {key[0]}/{key[1]}")
            index[key] = (dict(element), path, dict(payload.get("osm3s") or {}))
    return index, checksums


def _window_feature(site_id: str, topography: Mapping[str, Any], base: Path) -> tuple[dict[str, Any], dict[str, str]]:
    provenance = topography.get("provenance") or {}
    raster_path = Path(str(provenance.get("path", "")))
    if not raster_path.is_absolute():
        raster_path = base / raster_path
    if not raster_path.is_file():
        raise ValueError(f"missing Copernicus window for {site_id}: {raster_path}")
    sidecar = raster_path.with_suffix(raster_path.suffix + ".json")
    if not sidecar.is_file():
        raise ValueError(f"missing Copernicus provenance sidecar for {site_id}: {sidecar}")
    sidecar_payload = _load_json(sidecar)
    if sidecar_payload.get("checksum_sha256") != _sha256(raster_path):
        raise ValueError(f"Copernicus checksum mismatch for {site_id}: {raster_path}")
    try:
        import rasterio
        with rasterio.open(raster_path) as dataset:
            if str(dataset.crs) != "EPSG:4326":
                raise ValueError(f"Copernicus window must be EPSG:4326 for GeoJSON: {raster_path}")
            bounds = dataset.bounds
    except ImportError as exc:
        raise RuntimeError("rasterio is required to derive cached window footprints") from exc
    props = {"sample_id": site_id, "source_url": provenance.get("source_url"), "cache_status": provenance.get("status"),
             "window_status": topography.get("status"), "resolution_m": sidecar_payload.get("resolution_m"),
             "raster_sha256": sidecar_payload["checksum_sha256"], "raster_sidecar_sha256": _sha256(sidecar),
             "topography_status": topography.get("status")}
    geometry = {"type": "Polygon", "coordinates": [[[bounds.left, bounds.bottom], [bounds.right, bounds.bottom], [bounds.right, bounds.top], [bounds.left, bounds.top], [bounds.left, bounds.bottom]]]}
    return {"type": "Feature", "geometry": geometry, "properties": props}, {"path": str(raster_path.resolve()), "sha256": _sha256(raster_path), "sidecar_path": str(sidecar.resolve()), "sidecar_sha256": _sha256(sidecar)}


def _dem_fingerprint(site_id: str, topography: Mapping[str, Any], base: Path) -> dict[str, str]:
    """Fingerprint the exact cached window before choosing a bundle version."""
    provenance = topography.get("provenance") or {}
    raster_path = Path(str(provenance.get("path", "")))
    if not raster_path.is_absolute():
        raster_path = base / raster_path
    sidecar = raster_path.with_suffix(raster_path.suffix + ".json")
    if not raster_path.is_file() or not sidecar.is_file():
        raise ValueError(f"missing Copernicus window or sidecar for {site_id}: {raster_path}")
    payload = _load_json(sidecar)
    checksum = _sha256(raster_path)
    if payload.get("checksum_sha256") != checksum:
        raise ValueError(f"Copernicus checksum mismatch for {site_id}: {raster_path}")
    return {"sample_id": site_id, "path": str(raster_path.resolve()), "sha256": checksum,
            "sidecar_path": str(sidecar.resolve()), "sidecar_sha256": _sha256(sidecar)}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare_validation_assets(stage_json: str | Path, osm_matches_csv: str | Path, raw_osm_dir: str | Path, output_root: str | Path) -> Path:
    """Create a content-versioned offline artifact bundle and return its directory.

    Existing version directories are never rewritten.  A repeat call with the
    same frozen inputs returns the already-verified bundle.
    """
    stage_path, matches_path, raw_dir, destination = map(Path, (stage_json, osm_matches_csv, raw_osm_dir, output_root))
    stage = _load_json(stage_path)
    results = stage.get("results") if isinstance(stage, Mapping) else None
    if not isinstance(results, list) or not results:
        raise ValueError("stage JSON must contain non-empty results")
    if stage.get("stage_size") != len(results) or stage.get("validation", {}).get("actual_rows") != len(results):
        raise ValueError("stage JSON has inconsistent result count validation")
    site_ids = [str(row.get("site", {}).get("sample_id", "")) for row in results]
    if not all(site_ids) or len(set(site_ids)) != len(site_ids):
        raise ValueError("stage JSON has missing or duplicate sample_id values")
    matches = _read_matches(matches_path)
    missing = set(site_ids) - set(matches)
    if missing:
        raise ValueError(f"OSM match CSV is missing pilot sites: {sorted(missing)}")
    raw_index, raw_checksums = _raw_osm_index(raw_dir)
    # Fail before rendering any other artifact if the declared selected evidence
    # cannot be traced to a frozen payload.
    for site_id in site_ids:
        selected_type, selected_id = matches[site_id].get("selected_osm_type", ""), matches[site_id].get("selected_osm_id", "")
        if selected_type and selected_id and (selected_type, selected_id) not in raw_index:
            raise ValueError(f"selected OSM feature has no frozen raw geometry: {site_id} {selected_type}/{selected_id}")
    dem_fingerprints = [_dem_fingerprint(str(row["site"]["sample_id"]), row.get("topography") or {}, stage_path.parent) for row in results]
    input_manifest = {"schema_version": SCHEMA_VERSION, "stage_json": {"path": str(stage_path.resolve()), "sha256": _sha256(stage_path)},
                      "osm_matches_csv": {"path": str(matches_path.resolve()), "sha256": _sha256(matches_path)}, "raw_osm": raw_checksums,
                      "copernicus_windows": sorted(dem_fingerprints, key=lambda item: item["sample_id"])}
    version = f"{SCHEMA_VERSION}_{hashlib.sha256(_canonical(input_manifest)).hexdigest()[:16]}"
    final_dir = destination / version
    if final_dir.exists():
        manifest = final_dir / "manifest.json"
        if not manifest.is_file() or _load_json(manifest).get("input_manifest") != input_manifest:
            raise FileExistsError(f"refusing to overwrite existing artifact directory: {final_dir}")
        return final_dir

    stage_checksum = _sha256(stage_path)
    runtime = stage.get("runtime") or {}
    site_timings = {str(item.get("sample_id")): item.get("wall_time_s") for item in runtime.get("sites", []) if isinstance(item, Mapping)}
    ee_timing_definition = runtime.get("earth_engine_elapsed_definition")
    staged_version = f"{stage.get('stage', 'stage')}_{stage_checksum[:16]}"
    point_features: list[dict[str, Any]] = []; window_features: list[dict[str, Any]] = []; osm_features: list[dict[str, Any]] = []; dem_inputs: list[dict[str, str]] = []
    for result in sorted(results, key=lambda item: str(item["site"]["sample_id"])):
        site = result["site"]; site_id = str(site["sample_id"]); match = matches[site_id]
        merit = result.get("merit_hydro") or {}; merit_values = merit.get("values") or {}; merit_classes = merit.get("classification") or {}
        topo = result.get("topography") or {}
        # These stable, compact names are the App-facing contract.  The
        # flattened source fields below retain all original evidence as well.
        provenance = topo.get("provenance") or {}
        raster_path = Path(str(provenance.get("path", "")))
        if not raster_path.is_absolute(): raster_path = stage_path.parent / raster_path
        sidecar_payload = _load_json(raster_path.with_suffix(raster_path.suffix + ".json"))
        properties: dict[str, Any] = {"sample_id": site_id, "ecotype": site.get("Ecotype"),
            "latitude": float(site["Latitude"]), "longitude": float(site["Longitude"]),
            "population_name": site.get("Population.name"), "population_abbreviation": site.get("population.abbreviation"),
            "run_id": stage.get("run_id"), "run_stage": stage.get("stage"), "run_created_at_utc": stage.get("created_at_utc"),
            "run_version": staged_version, "staged_output_checksum_sha256": stage_checksum,
            "site_runtime_wall_time_s": site_timings.get(site_id),
            # The completed run retained a total EE client time but not a
            # per-site breakdown; null avoids misrepresenting a derived value.
            "ee_client_round_trip_s": None, "ee_timing_definition": ee_timing_definition,
            "terrain_elevation_m": topo.get("elevation_m"), "terrain_slope_degrees": topo.get("slope_degrees"),
            "terrain_local_relief_m": topo.get("local_relief_m"), "terrain_status": topo.get("status"),
            "copernicus_window_checksum_sha256": sidecar_payload.get("checksum_sha256"),
            "copernicus_source_url": provenance.get("source_url"), "copernicus_retrieval_utc": sidecar_payload.get("retrieval_date"),
            "merit_dataset": merit.get("dataset"), "merit_sampling_scale_m": merit.get("sampling_scale_m")}
        for band in ("elv", "dir", "upa", "upg", "hnd", "wat", "wth"):
            properties[f"merit_{band}"] = merit_values.get(band)
            properties[f"merit_{band}_status"] = merit_classes.get(band)
        _flatten("site", site, properties); _flatten("topography", result.get("topography") or {}, properties)
        _flatten("merit_hydro", result.get("merit_hydro") or {}, properties); _flatten("hydrology", result.get("hydrology") or {}, properties)
        for key, value in sorted(match.items()): properties[f"osm_{key}"] = value if value != "" else None
        point_features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(site["Longitude"]), float(site["Latitude"])]}, "properties": properties})
        window, dem_record = _window_feature(site_id, result.get("topography") or {}, stage_path.parent)
        window_features.append(window); dem_inputs.append(dem_record)
        osm_type, osm_id = match.get("selected_osm_type", ""), match.get("selected_osm_id", "")
        osm_props = {"sample_id": site_id, "osm_type": osm_type or None, "osm_id": osm_id or None,
            "selected_osm_type": osm_type or None, "selected_osm_id": osm_id or None,
            "water_feature_class": match.get("water_feature_class") or None, "match_method": match.get("match_method") or None,
            "match_distance_m": float(match["match_distance_m"]) if match.get("match_distance_m") else None,
            "manual_review": match.get("manual_review") == "True", "query_source": match.get("query_source") or None,
            "query_date": match.get("osm_query_date") or None, "failure_diagnostics": match.get("failure_diagnostics") or None}
        if osm_type and osm_id:
            cached = raw_index.get((osm_type, osm_id))
            if cached is None:
                raise ValueError(f"selected OSM feature has no frozen raw geometry: {site_id} {osm_type}/{osm_id}")
            element, source_path, osm3s = cached; geometry = _overpass_geometry(element)
            if geometry is None:
                raise ValueError(f"selected OSM feature has invalid raw geometry: {site_id} {osm_type}/{osm_id}")
            osm_props.update({"evidence_status": "selected_geometry_frozen", "osm_tags_json": json.dumps(element.get("tags") or {}, sort_keys=True),
                "raw_response_path": str(source_path.resolve()), "raw_response_sha256": _sha256(source_path), "osm_base_timestamp": osm3s.get("timestamp_osm_base"),
                "snapshot_utc": osm3s.get("timestamp_osm_base"), "snapshot_checksum_sha256": _sha256(source_path),
                "match_status": "matched_frozen_geometry"})
            osm_features.append({"type": "Feature", "geometry": geometry, "properties": osm_props})
        else:
            # Keep every pilot point inspectable when no geometry was selected;
            # the point geometry is explicitly an evidence fallback, not water.
            osm_props["evidence_status"] = "no_selected_feature"
            osm_props["snapshot_utc"] = None; osm_props["snapshot_checksum_sha256"] = None
            osm_props["match_status"] = "source_unavailable" if match.get("query_source") == "failed" else "unmatched_no_selected_feature"
            osm_features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(site["Longitude"]), float(site["Latitude"])]}, "properties": osm_props})

    artifacts = {"pilot_sites.geojson": {"type": "FeatureCollection", "features": point_features},
                 "copernicus_windows.geojson": {"type": "FeatureCollection", "features": window_features},
                 "osm_matched_features.geojson": {"type": "FeatureCollection", "features": osm_features}}
    destination.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{version}.", dir=destination))
    try:
        for filename, payload in artifacts.items(): _write_json(temp_dir / filename, payload)
        # CSV uses the same flattened point properties and is ready for table-asset upload.
        fields = sorted({key for feature in point_features for key in feature["properties"]})
        with (temp_dir / "pilot_sites.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise"); writer.writeheader()
            for feature in point_features: writer.writerow(feature["properties"])
        artifact_checksums = {path.name: _sha256(path) for path in sorted(temp_dir.iterdir()) if path.is_file()}
        manifest = {"schema_version": SCHEMA_VERSION, "bundle_version": version, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "offline_only": True, "earth_engine_actions": "none", "input_manifest": input_manifest, "copernicus_inputs": sorted(dem_inputs, key=lambda x: x["path"]),
                    "counts": {"pilot_sites": len(point_features), "copernicus_windows": len(window_features), "osm_matched_features": len(osm_features)},
                    "artifacts": artifact_checksums}
        _write_json(temp_dir / "manifest.json", manifest)
        os.replace(temp_dir, final_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return final_dir
