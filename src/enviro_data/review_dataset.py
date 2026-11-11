"""Assemble the immutable full input and provisional environmental evidence."""

from __future__ import annotations
import csv, json
from collections import Counter
from pathlib import Path
from dataclasses import asdict
from .input import load_sites
from .site_habitat import infer_site_habitat
from .river_sources import sha

LAKE_METRICS = (
    "lake_area_m2",
    "lake_perimeter_m",
    "lake_area_perimeter_m",
    "lake_shoreline_development",
)


def read_json(path, default):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def build(
    source, point_file, lake_file, river_dir, shoreline_file, cached_pilot, output_dir
):
    source = Path(source)
    records = load_sites(source, strict=True).records
    points = read_json(point_file, {"sites": {}, "sources": {}})
    lakes = read_json(lake_file, {})
    shores = read_json(shoreline_file, {})
    rivers = {}
    for p in Path(river_dir).glob("checkpoints/*.json"):
        value = json.loads(p.read_text())
        rivers[value["sample_id"]] = value
    with Path(cached_pilot).open(encoding="utf-8-sig") as f:
        cached = {r["sample_id"]: r for r in csv.DictReader(f)}
    rows = []
    climate_columns = [
        "climate_period",
        "mean_annual_air_temperature_c",
        "annual_mean_precipitation_mm_day",
        "warmest_month_mean_air_temperature_c",
        "coldest_month_mean_air_temperature_c",
        "monthly_mean_air_temperature_range_c",
    ]
    for month in (
        "jan",
        "feb",
        "mar",
        "apr",
        "may",
        "jun",
        "jul",
        "aug",
        "sep",
        "oct",
        "nov",
        "dec",
    ):
        climate_columns.extend(
            (f"air_temperature_{month}_c", f"precipitation_{month}_mm_day")
        )
    for r in records:
        inference = infer_site_habitat(r.population_name, r.ecotype)
        kind = inference.working_waterbody_type
        point = points["sites"].get(r.sample_id, {})
        if point and (
            point.get("latitude") != r.latitude or point.get("longitude") != r.longitude
        ):
            raise ValueError(f"point coordinate mismatch: {r.sample_id}")
        row = {
            "sample_id": r.sample_id,
            "population_name": r.population_name,
            "population_abbreviation": r.population_abbreviation,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "source_ecotype": r.ecotype,
            **asdict(inference),
            "matched_terms": ";".join(inference.matched_terms),
            "classification_status": "provisional_unverified",
            "review_required": True,
            "reviewed_waterbody_class": "",
            "reviewed_waterbody_name": "",
            "reviewed_latitude": "",
            "reviewed_longitude": "",
            "reviewer": "",
            "review_notes": "",
            "point_elevation_m": point.get("point_elevation_m"),
            "point_elevation_status": point.get(
                "point_elevation_status", "not_collected"
            ),
            "point_elevation_source_key": point.get("elevation_source_key"),
            "climate_status": point.get("climate_status", "not_collected"),
            "climate_source_key": point.get("climate_source_key"),
            "climate_query_latitude": point.get("climate_query_latitude"),
            "climate_query_longitude": point.get("climate_query_longitude"),
            "climate_grid_latitude": point.get("climate_grid_latitude"),
            "climate_grid_longitude": point.get("climate_grid_longitude"),
            "climate_sampling_method": point.get("climate_sampling_method"),
        }
        row.update({c: point.get(c) for c in climate_columns})
        old = cached.get(r.sample_id, {})
        if old and (
            abs(float(old["latitude"]) - r.latitude) > 1e-10
            or abs(float(old["longitude"]) - r.longitude) > 1e-10
        ):
            raise ValueError("frozen pilot coordinates do not match current input")
        for name in (
            "local_terrain_elevation_m",
            "local_terrain_slope_deg",
            "local_terrain_relief_m",
            "merit_elevation_m",
            "upstream_drainage_area_km2",
            "upstream_drainage_pixels",
        ):
            row["cached_point_" + name] = old.get(name) or None
            row["cached_point_" + name + "__status"] = old.get(
                name + "__status", "not_in_frozen_pilot"
            )
        lake = lakes.get(r.sample_id, {}) if kind == "lake" else {}
        row["lake_geometry_status"] = (
            lake.get("status", "not_collected")
            if kind == "lake"
            else "not_applicable_or_class_unresolved"
        )
        row["lake_geometry_source"] = lake.get("source")
        row["lake_hylak_id"] = lake.get("hylak_id")
        row["lake_name_evidence"] = lake.get("name_evidence")
        row["lake_osm_type"] = lake.get("osm_type")
        row["lake_osm_id"] = lake.get("osm_id")
        row["lake_osm_waterbody_type"] = lake.get("osm_waterbody_type")
        row["lake_geometry_sha256"] = lake.get("sha256")
        for name in LAKE_METRICS:
            row[name] = lake.get(name)
        row["lake_geometry_resolution_status"] = (
            "raw_source_resolution_not_normalized" if lake else None
        )
        row["river_flow_connection_verified"] = False if kind == "stream" else None
        row["lake_metrics_status"] = (
            "provisional_identity_review_required"
            if lake.get("status") == "candidate_polygon"
            else row["lake_geometry_status"]
        )
        river = rivers.get(r.sample_id, {}) if kind == "stream" else {}
        snap = river.get("snap", {})
        selected = snap.get("selected") or {}
        attributes = river.get("reach_attributes", {})
        row["river_vector_status"] = (
            snap.get("status", "not_collected")
            if kind == "stream"
            else "not_applicable_or_class_unresolved"
        )
        row["river_reach_id"] = selected.get("reach_id")
        row["river_snap_distance_m"] = selected.get("distance_m")
        row["river_snapped_latitude"] = selected.get("latitude")
        row["river_snapped_longitude"] = selected.get("longitude")
        row["river_reach_upstream_area_km2"] = attributes.get("UPLAND_SKM")
        row["river_reach_strahler_order"] = attributes.get("ORD_STRA")
        row["river_reach_average_discharge_m3_s"] = attributes.get("DIS_AV_CMS")
        row["river_reach_attributes_status"] = (
            "provisional_reach_outlet_value"
            if attributes.get("UPLAND_SKM") is not None
            else row["river_vector_status"]
        )
        row["river_merit_alignment_status"] = (
            river.get("alignment", {}).get("status", "not_collected")
            if kind == "stream"
            else "not_applicable_or_class_unresolved"
        )
        for name in (
            "upstream_drainage_area_km2",
            "upstream_drainage_pixels",
            "channel_width_m",
        ):
            row["river_snapped_" + name] = (
                river.get("metrics", {}).get(name, {}).get("channel")
            )
        shore = shores.get(r.sample_id, {}) if kind == "lake" else {}
        row["shoreline_elevation_status"] = (
            shore.get("status", "lake_geometry_or_terrain_missing")
            if kind == "lake"
            else "not_applicable_or_class_unresolved"
        )
        row["shoreline_elevation_source"] = (
            "Copernicus GLO-90 DSM; nearest native cells" if shore.get("plan") else None
        )
        row["lake_surface_dem_proxy_m"] = shore.get("lake_surface_dem_proxy_m")
        row["lake_surface_dem_range_m"] = shore.get("lake_surface_dem_range_m")
        for radius in (50, 100, 250):
            ring = shore.get("rings", {}).get(str(radius), {})
            for name in (
                "sample_count",
                "mean_relative_elevation_m",
                "median_relative_elevation_m",
                "p90_relative_elevation_m",
            ):
                row[f"shore_{radius}m_" + name] = ring.get(name)
        row["shoreline_slope_degrees"] = None
        row["shoreline_slope_status"] = "deferred"
        row["lake_depth_estimate_m"] = None
        row["lake_depth_status"] = (
            "thesis_equation_and_variable_buffer_rule_pending"
            if kind == "lake"
            else "not_applicable_or_class_unresolved"
        )
        row["marine_specific_metrics"] = None
        row["marine_metrics_status"] = (
            "deferred" if kind == "marine" else "not_applicable"
        )
        rows.append(row)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "stickleback_full_review_v1.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "rows": len(rows),
        "ids_unique": len({r["sample_id"] for r in rows}) == len(rows),
        "source_sha256": sha(source),
        "review_table_sha256": sha(out / "stickleback_full_review_v1.csv"),
        "working_classes": dict(Counter(r["working_waterbody_type"] for r in rows)),
        "point_elevation": dict(Counter(r["point_elevation_status"] for r in rows)),
        "climate": dict(Counter(r["climate_status"] for r in rows)),
        "lake_polygons": sum(r["lake_area_m2"] is not None for r in rows),
        "river_reach_upstream_areas": sum(
            r["river_reach_upstream_area_km2"] is not None for r in rows
        ),
        "river_snapped_merit_areas": sum(
            r["river_snapped_upstream_drainage_area_km2"] is not None for r in rows
        ),
        "shoreline_profiles": dict(
            Counter(
                r["shoreline_elevation_status"]
                for r in rows
                if r["working_waterbody_type"] == "lake"
            )
        ),
        "climate_periods": sorted(
            {r["climate_period"] for r in rows if r["climate_period"]}
        ),
        "climate_unique_nominal_grid_cells": len(
            {
                (r["climate_grid_latitude"], r["climate_grid_longitude"])
                for r in rows
                if r["climate_status"] == "ok"
            }
        ),
        "confirmed_habitat_labels": 0,
    }
    (out / "coverage_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    sources = {
        "point_sources": points["sources"],
        "lake_results": lakes,
        "river_sources": [r.get("provenance") for r in rivers.values()],
        "frozen_pilot": {"path": str(cached_pilot), "sha256": sha(cached_pilot)},
        "shoreline_results": shores,
    }
    (out / "source_provenance.json").write_text(json.dumps(sources, indent=2) + "\n")
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["longitude"], r["latitude"]],
            },
            "properties": {
                "sample_id": r["sample_id"],
                "population_name": r["population_name"],
                "inferred_class": r["working_waterbody_type"],
                "review_required": True,
            },
        }
        for r in rows
    ]
    (out / "sample_points.geojson").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features}, ensure_ascii=False
        )
        + "\n"
    )
    return summary
