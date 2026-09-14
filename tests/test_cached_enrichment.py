import csv
import math

from enviro_data.cached_enrichment import enrich_cached_row, write_enriched_csv


def freshwater_row():
    return {
        "sample_id": "S1", "population_name": "River", "ecotype": "freshwater",
        "latitude": "49", "longitude": "-123", "merit_dataset": "MERIT/Hydro/v1_0_1",
        "merit_sampling_scale_m": "90", "merit_upa": "9", "merit_upa_status": "valid_value",
        "merit_hnd": "2.5", "merit_hnd_status": "valid_value", "merit_wth": "",
        "merit_wth_status": "nodata_or_masked", "merit_elv": "100", "merit_elv_status": "valid_value",
        "merit_upg": "3", "merit_upg_status": "valid_value", "merit_dir": "8",
        "merit_dir_status": "valid_value", "merit_wat": "0", "merit_wat_status": "valid_value",
        "terrain_elevation_m": "101", "terrain_slope_degrees": "45", "terrain_local_relief_m": "5",
        "terrain_status": "ok", "copernicus_retrieval_utc": "2026-01-01T00:00:00Z",
        "copernicus_window_checksum_sha256": "abc",
    }


def indexed(row):
    return {metric.name: metric for metric in enrich_cached_row(row)}


def test_cached_merit_and_terrain_values_become_metrics():
    metrics = indexed(freshwater_row())
    assert metrics["upstream_drainage_area_km2"].value == 9
    assert metrics["upstream_drainage_area_km2"].status == "ok"
    assert metrics["channel_width_m"].value is None
    assert metrics["channel_width_m"].status == "no_valid_data"
    assert metrics["log10_upstream_drainage_area"].value == 1
    assert math.isclose(metrics["local_terrain_gradient"].value, 1)
    assert metrics["local_terrain_gradient"].diagnostics["derivation"].endswith("not channel gradient")


def test_marine_values_are_not_applicable_even_if_stale_values_exist():
    row = freshwater_row() | {"ecotype": "marine"}
    metrics = indexed(row)
    assert metrics["upstream_drainage_area_km2"].value is None
    assert metrics["upstream_drainage_area_km2"].status == "not_applicable"
    assert metrics["local_terrain_slope_deg"].status == "not_applicable"
    assert metrics["log10_upstream_drainage_area"].value is None


def test_enriched_csv_preserves_values_statuses_and_sources(tmp_path):
    path = write_enriched_csv([freshwater_row()], tmp_path / "metrics.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["habitat_domain"] == "freshwater"
    assert row["upstream_drainage_area_km2"] == "9.0"
    assert row["upstream_drainage_area_km2__status"] == "ok"
    assert row["upstream_drainage_area_km2__source"] == "MERIT/Hydro/v1_0_1"
    assert row["local_terrain_elevation_m__checksum_sha256"] == "abc"
    assert row["local_terrain_gradient__diagnostics"].endswith('not channel gradient"}')
