import csv, json
from pathlib import Path
import pytest
from enviro_data.shoreline import sample_plan, summarize
from enviro_data.review_dataset import build
from scripts.prepare_hydrolakes_review import prepare


def test_shoreline_relative_elevation_and_unstable_proxy():
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [[-0.01, -0.01], [0.01, -0.01], [0.01, 0.01], [-0.01, 0.01], [-0.01, -0.01]]
        ],
    }
    plan = sample_plan(geometry)
    values = []
    for name, points in plan["groups"].items():
        values.extend([10 if name == "lake_surface" else 15] * len(points))
    result = summarize(plan, values)
    assert result["status"] == "exploratory"
    assert result["rings"]["100"]["mean_relative_elevation_m"] == 5
    assert (
        result["depth_estimate_m"] is None and result["shoreline_slope_degrees"] is None
    )
    values[0] = 30
    result = summarize(plan, values)
    assert result["status"] == "lake_surface_proxy_unstable_or_insufficient"
    assert result["rings"]["100"]["mean_relative_elevation_m"] is None
    with pytest.raises(ValueError, match="count"):
        summarize(plan, [10])


def write_sites(path, records):
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "sample_id",
                "Population.name",
                "population.abbreviation",
                "Latitude",
                "Longitude",
                "Ecotype",
            ]
        )
        w.writerows(records)


def test_full_assembly_preserves_ids_labels_missingness_and_marine_blank(tmp_path):
    source = tmp_path / "sites.csv"
    write_sites(
        source,
        [
            ["S1", "Lake Clear", "LC", 1, 2, "freshwater"],
            ["S2", "Ocean", "O", 3, 4, "marine"],
        ],
    )
    point = tmp_path / "point.json"
    point.write_text(
        json.dumps(
            {
                "sites": {
                    "S1": {
                        "latitude": 1,
                        "longitude": 2,
                        "point_elevation_m": 0,
                        "point_elevation_status": "ok",
                    }
                },
                "sources": {},
            }
        )
    )
    lake = tmp_path / "lake.json"
    lake.write_text(
        json.dumps(
            {
                "S1": {
                    "status": "candidate_polygon",
                    "lake_area_m2": 100,
                    "lake_perimeter_m": 40,
                    "lake_area_perimeter_m": 2.5,
                }
            }
        )
    )
    cached = tmp_path / "cached.csv"
    cached.write_text("sample_id,latitude,longitude\n")
    result = build(
        source,
        point,
        lake,
        tmp_path / "rivers",
        tmp_path / "shore.json",
        cached,
        tmp_path / "out",
    )
    assert result["rows"] == 2 and result["ids_unique"]
    with (tmp_path / "out/stickleback_full_review_v1.csv").open(
        encoding="utf-8-sig"
    ) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["point_elevation_m"] == "0"
    assert rows[0]["reviewed_waterbody_class"] == ""
    assert rows[1]["marine_specific_metrics"] == "" and rows[1]["lake_area_m2"] == ""
    assert rows[1]["climate_status"] == "not_collected"
    bad = json.loads(point.read_text())
    bad["sites"]["S1"]["latitude"] = 1.1
    point.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="coordinate mismatch"):
        build(
            source,
            point,
            lake,
            tmp_path / "rivers",
            tmp_path / "shore.json",
            cached,
            tmp_path / "bad",
        )


def test_local_hydrolakes_bbox_scan_preserves_holes_and_metrics(tmp_path):
    import shapefile, zipfile
    from rasterio.crs import CRS

    source = tmp_path / "sites.csv"
    write_sites(
        source,
        [
            ["S1", "Lake One", "L1", 0.5, 0.5, "freshwater"],
            ["S2", "Lake Two", "L2", 1.5, 1.5, "freshwater"],
        ],
    )
    original = tmp_path / "original"
    original.mkdir()
    shp = original / "lakes.shp"
    with shapefile.Writer(str(shp), shapeType=shapefile.POLYGON) as w:
        w.field("Hylak_id", "N")
        w.field("Lake_type", "N")
        w.poly(
            [
                [(0, 0), (0, 4), (4, 4), (4, 0), (0, 0)],
                [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)],
            ]
        )
        w.record(1, 1)
    shp.with_suffix(".prj").write_text(CRS.from_epsg(4326).to_wkt())
    out = tmp_path / "hydrolakes"
    out.mkdir()
    with zipfile.ZipFile(out / "HydroLAKES_polys_v10_shp.zip", "w") as z:
        for p in original.iterdir():
            z.write(p, p.name)
    result = prepare(source, out)
    assert result["candidate_polygon_sites"] == 1
    results = json.loads((out / "lake_results.json").read_text())
    assert results["S1"]["hylak_id"] == 1 and "S2" not in results
    assert results["S1"]["lake_area_m2"] > 0 and results["S1"]["review_required"]
