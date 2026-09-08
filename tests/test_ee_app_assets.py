from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import pytest

from enviro_data.ee_app_assets import prepare_validation_assets


def _write_fixture(root: Path) -> tuple[Path, Path, Path]:
    stage = {"stage_size": 1, "validation": {"actual_rows": 1}, "results": [{"site": {"sample_id": "S0001", "Latitude": "1.5", "Longitude": "2.5", "Ecotype": "marine"}, "topography": {"status": "no_valid_dem_data", "elevation_m": None, "provenance": {"path": str(root / "S0001_copernicus_3x3.tif"), "status": "cache_hit", "source_url": "frozen"}}, "merit_hydro": {"values": {"elv": None}, "classification": {"elv": "nodata_or_masked"}}, "hydrology": {"status": "not_applicable_marine"}}]}
    stage_path = root / "stage.json"; stage_path.write_text(json.dumps(stage), encoding="utf-8")
    # A tiny valid WGS84 GeoTIFF gives the footprint code a real raster to inspect.
    raster = root / "S0001_copernicus_3x3.tif"
    raster.write_bytes(b"fixture-raster")
    sidecar = {"checksum_sha256": hashlib.sha256(raster.read_bytes()).hexdigest()}
    raster.with_suffix(".tif.json").write_text(json.dumps(sidecar), encoding="utf-8")
    matches = root / "matches.csv"
    with matches.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "selected_osm_type", "selected_osm_id", "water_feature_class", "match_method", "match_distance_m", "manual_review"]); writer.writeheader(); writer.writerow({"sample_id": "S0001", "selected_osm_type": "way", "selected_osm_id": "7", "water_feature_class": "stream", "match_method": "nearest_feature", "match_distance_m": "4.0", "manual_review": "False"})
    raw_dir = root / "raw"; raw_dir.mkdir(); (raw_dir / "response.json").write_text(json.dumps({"osm3s": {"timestamp_osm_base": "2026-01-01T00:00:00Z"}, "elements": [{"type": "way", "id": 7, "tags": {"waterway": "stream"}, "geometry": [{"lon": 2.5, "lat": 1.5}, {"lon": 2.6, "lat": 1.6}]}]}), encoding="utf-8")
    return stage_path, matches, raw_dir


def test_prepare_assets_preserves_nulls_and_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage, matches, raw = _write_fixture(tmp_path)
    class Bounds: left, bottom, right, top = 2.4, 1.4, 2.6, 1.6
    class Dataset:
        crs = "EPSG:4326"; bounds = Bounds()
        def __enter__(self): return self
        def __exit__(self, *_): return False
    import rasterio
    monkeypatch.setattr(rasterio, "open", lambda _: Dataset())
    out = prepare_validation_assets(stage, matches, raw, tmp_path / "output")
    assert out == prepare_validation_assets(stage, matches, raw, tmp_path / "output")
    manifest = json.loads((out / "manifest.json").read_text())
    points = json.loads((out / "pilot_sites.geojson").read_text())["features"]
    assert manifest["offline_only"] is True and manifest["earth_engine_actions"] == "none"
    assert points[0]["properties"]["merit_elv"] is None
    assert points[0]["properties"]["merit_elv_status"] == "nodata_or_masked"
    assert points[0]["properties"]["terrain_status"] == "no_valid_dem_data"
    assert points[0]["properties"]["latitude"] == 1.5
    assert points[0]["properties"]["staged_output_checksum_sha256"]
    assert points[0]["properties"]["ee_client_round_trip_s"] is None
    assert json.loads((out / "osm_matched_features.geojson").read_text())["features"][0]["properties"]["osm_id"] == "7"
    osm = json.loads((out / "osm_matched_features.geojson").read_text())["features"][0]["properties"]
    assert osm["selected_osm_id"] == "7"
    assert osm["snapshot_checksum_sha256"]
    assert osm["match_status"] == "matched_frozen_geometry"
    for filename in ("pilot_sites.geojson", "osm_matched_features.geojson", "copernicus_windows.geojson"):
        features = json.loads((out / filename).read_text())["features"]
        assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) for feature in features for key in feature["properties"])


def test_rejects_selected_osm_geometry_absent_from_frozen_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stage, matches, raw = _write_fixture(tmp_path)
    (raw / "response.json").write_text('{"elements": []}', encoding="utf-8")
    import rasterio
    monkeypatch.setattr(rasterio, "open", lambda _: None)
    with pytest.raises(ValueError, match="no frozen raw geometry"):
        prepare_validation_assets(stage, matches, raw, tmp_path / "output")
