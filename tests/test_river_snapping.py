import csv
import json
import pytest
from enviro_data.river_snapping import (
    snap_stream,
    align_merit_cell,
    comparison_metrics,
    nearest_on_geometry,
)
from enviro_data.river_sources import BANDS, local_merit, merit_window
from scripts.run_river_pilot import run


def row(**changes):
    return {
        "sample_id": "S1",
        "Population.name": "Test River",
        "population.abbreviation": "T",
        "Longitude": "0",
        "Latitude": "0",
        "Ecotype": "freshwater",
        "pilot_class": "stream",
        "validation_role": "core",
        **changes,
    }


def line(identity="way/1", latitude=0.0, name="Test River"):
    return {
        "id": identity,
        "properties": {"waterway": "river", "name": name},
        "geometry": {
            "type": "LineString",
            "coordinates": [[-0.01, latitude], [0.01, latitude]],
        },
    }


def cell(lon=0.0, area=10.0, width=5.0):
    return {
        "longitude": lon,
        "latitude": 0.0,
        "values": {"upa": area, "upg": 100, "wth": width, "dir": 1, "elv": 0},
    }


def test_vector_snap_and_ambiguity():
    snap = snap_stream(row(Latitude=".001"), [line()])
    assert 110 < snap["selected"]["distance_m"] < 112
    assert snap["review_required"] and not snap["flow_connection_verified"]
    assert (
        snap_stream(row(), [line(), line("way/2", 0.0001)])["status"]
        == "ambiguous_reaches"
    )
    assert snap_stream(row(), [line(latitude=0.01)])["status"] == "no_candidate"
    assert snap_stream(row(), [line(name="Other River")])["status"] == "name_conflict"
    assert snap_stream(row(validation_role="challenge"), [line()])["selected"] is None
    assert (
        snap_stream(row(Ecotype="marine"), [line()])["status"]
        == "classification_review_required"
    )


def test_dateline_invalid_and_bounds():
    geometry = {"type": "LineString", "coordinates": [[179.999, 0], [-179.999, 0]]}
    assert nearest_on_geometry((180, 0.001), geometry)["distance_m"] < 112
    invalid = line()
    invalid["geometry"]["coordinates"][0][0] = float("nan")
    assert snap_stream(row(), [invalid])["rejected"]
    with pytest.raises(ValueError):
        snap_stream(row(), [], max_distance_m=1000)


def test_merit_not_max_accumulation_and_zero_preserved():
    snap = snap_stream(row(), [line()])
    result = align_merit_cell(snap, [cell(), cell(0.001, area=1000)])
    assert result["selected"]["values"]["upa"] == 10
    assert align_merit_cell(snap, [cell(width=0)])["selected"] is None
    assert align_merit_cell(snap, [cell(area=-9999)])["selected"] is None
    assert (
        align_merit_cell(snap, [cell(), cell(0.0001, area=1000)])["status"]
        == "ambiguous_channel_cells"
    )
    metrics = comparison_metrics({"upa": 0, "upg": -9999, "wth": float("nan")}, result)
    assert metrics["upstream_drainage_area_km2"]["delta"] == 10
    assert metrics["upstream_drainage_pixels"]["original"] is None
    assert metrics["channel_width_m"]["original"] is None


def make_rasters(tmp_path, bad=False):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    paths = {}
    for band in BANDS:
        path = tmp_path / f"{band}.tif"
        paths[band] = path.name
        value = {"upa": 10, "upg": 100, "wth": 5, "dir": 1, "elv": 0, "wat": 1}[band]
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=9,
            width=9,
            count=1,
            dtype="float32",
            nodata=-9999,
            crs="EPSG:4326",
            transform=from_origin(
                -0.00375, 0.00375, 0.001 if bad else 1 / 1200, 1 / 1200
            ),
        ) as ds:
            ds.write(np.full((9, 9), value, dtype="float32"), 1)
    config = tmp_path / "merit.json"
    config.write_text(json.dumps({"dataset": "MERIT/Hydro/v1_0_1", "bands": paths}))
    return config


def test_local_native_grid_and_missingness(tmp_path):
    config = make_rasters(tmp_path)
    result = local_merit(config, (0, 0), (0, 0))
    assert result["original"]["elv"] == 0 and result["original"]["upa"] == 10
    assert 1 < len(result["cells"]) <= 400
    assert all(
        v is None for v in local_merit(config, (1, 1), None)["original"].values()
    )
    make_rasters(tmp_path, bad=True)
    with pytest.raises(ValueError, match="native 3 arc-second"):
        local_merit(config, (0, 0), (0, 0))


def test_cache_only_never_starts_ee(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("network started")
    )
    with pytest.raises(RuntimeError, match="cache_missing"):
        merit_window((0, 0), None, tmp_path)


def test_offline_end_to_end(tmp_path):
    config = make_rasters(tmp_path)
    source = tmp_path / "sites.csv"
    with source.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row()))
        w.writeheader()
        w.writerow(row())
    vectors = tmp_path / "vectors.geojson"
    vectors.write_text(json.dumps({"type": "FeatureCollection", "features": [line()]}))
    out = tmp_path / "results"
    assert run(source, out, vectors=vectors, merit_rasters=config)["metrics_complete"]
    result = json.loads((out / "checkpoints/S1.json").read_text())
    assert result["metrics"]["upstream_drainage_area_km2"]["channel"] == 10
    assert result["review_required"]
    with pytest.raises(ValueError, match="configuration differs"):
        run(source, out, vectors=vectors, merit_rasters=config, max_distance=100)
