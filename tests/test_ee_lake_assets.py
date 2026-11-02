import csv
import json

import pytest

from enviro_data.ee_lake_assets import prepare_lake_validation_assets


def fixture_run(path):
    path.mkdir()
    with (path / "lake_polygon_pilot.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sample_id", "longitude", "latitude", "status"])
        writer.writeheader()
        writer.writerows([{"sample_id": "S1", "longitude": -21.1, "latitude": 64.2, "status": "candidate_polygon"},
                          {"sample_id": "S2", "longitude": 1, "latitude": 2, "status": "unresolved"}])
    polygon = {"type": "Feature", "properties": {"sample_id": "S1", "osm_type": "way", "osm_id": "7",
               "tags": {"water": "lake"}, "absent": None},
               "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 1], [0, 0]]]}}
    (path / "lake_polygon_pilot.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [polygon]}))
    (path / "candidate_polygons").mkdir()
    (path / "candidate_polygons/a.geojson").write_text(json.dumps(polygon))
    polygon["properties"]["osm_id"] = "8"
    polygon["properties"]["tags"]["water"] = "reservoir"
    (path / "candidate_polygons/b.geojson").write_text(json.dumps(polygon))
    (path / "candidate_discovery.jsonl").write_text(json.dumps({"sample_id": "S2", "candidates": [{"osm_id": "9"}]}))
    for name in ["candidate_outcomes.jsonl", "selection_manifest.json", "run_metadata.json"]:
        (path / name).write_text("{}")


def test_preserves_unresolved_sites_neighbours_and_frozen_inputs(tmp_path):
    run = tmp_path / "run"
    fixture_run(run)
    before = {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    bundle = prepare_lake_validation_assets(run, tmp_path / "output")
    sites = json.loads((bundle / "lake_sites.geojson").read_text())["features"]
    assert sites[0]["geometry"]["coordinates"] == [-21.1, 64.2]
    assert sites[1]["properties"]["status"] == "unresolved"
    assert '"osm_id":"9"' in sites[1]["properties"]["discovery_evidence"]
    polygons = json.loads((bundle / "evaluated_polygons.geojson").read_text())["features"]
    assert [f["properties"]["selected_candidate"] for f in polygons] == [True, False]
    assert polygons[1]["properties"]["tags"] == '{"water":"reservoir"}'
    assert polygons[0]["properties"]["absent"] is None
    assert all(f["properties"]["review_required"] for f in sites + polygons)
    assert before == {p.relative_to(run): p.read_bytes() for p in run.rglob("*") if p.is_file()}
    assert prepare_lake_validation_assets(run, tmp_path / "output") == bundle
    (bundle / "lake_sites.geojson").write_text("changed")
    with pytest.raises(ValueError, match="immutable bundle differs"):
        prepare_lake_validation_assets(run, tmp_path / "output")
