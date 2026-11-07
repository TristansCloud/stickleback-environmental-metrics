"""Pilot-gated full review generation with offline hydrology fallbacks."""

from __future__ import annotations
import argparse, csv, json, logging
from pathlib import Path
from scripts.collect_point_review_data import run as collect_points
from scripts.collect_lake_review import run as collect_lakes
from scripts.prepare_hydrorivers_vectors import prepare as prepare_rivers
from scripts.prepare_hydrolakes_review import prepare as prepare_lakes
from scripts.run_river_pilot import run as match_rivers
from scripts.collect_shoreline_review import run as collect_shores
from enviro_data.lake_lookup import atomic_json
from enviro_data.review_dataset import build, read_json
from enviro_data.site_habitat import infer_site_habitat

ROOT = Path(__file__).resolve().parents[1]


def csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def combine_lakes(osm_dir, hydro_dir, output_dir):
    hydro = read_json(hydro_dir / "lake_results.json", {})
    osm = read_json(osm_dir / "lake_results.json", {})
    combined = dict(hydro)
    for sid, value in osm.items():
        if value["status"] == "candidate_polygon" or sid not in combined:
            combined[sid] = {**value, "source": "OpenStreetMap"}
    features = {}
    for directory in (hydro_dir, osm_dir):
        for feature in read_json(directory / "lake_polygons.geojson", {"features": []})[
            "features"
        ]:
            sid = feature["properties"]["sample_id"]
            if directory == osm_dir and combined[sid].get("source") != "OpenStreetMap":
                continue
            features[sid] = {**feature, "properties": combined[sid]}
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "lake_results.json", combined)
    atomic_json(
        output_dir / "lake_polygons.geojson",
        {"type": "FeatureCollection", "features": list(features.values())},
    )
    return {
        "candidate_sites": sum(
            r["status"] == "candidate_polygon" for r in combined.values()
        )
    }


def run(live=False):
    cache = ROOT / "data/cache"
    cache.mkdir(exist_ok=True)
    source = ROOT / "site_overview_v1_clean.csv"
    stages = {}

    def checkpoint(stage, result):
        stages[stage] = result
        atomic_json(cache / "generation_stages.json", stages)

    pilot = []
    for kind in ("stream", "marine", "transition"):
        pilot.extend(csv_rows(ROOT / f"data/habitat_pilots/{kind}_pilot_sites_v1.csv"))
    pilot.extend(csv_rows(ROOT / "data/lake_pilot_sites_v1.csv")[:5])
    fields = [
        "sample_id",
        "Population.name",
        "population.abbreviation",
        "Latitude",
        "Longitude",
        "Ecotype",
    ]
    pilot_source = cache / "point_review/pilot_sites.csv"
    write_rows(pilot_source, pilot, fields)
    summary = collect_points(
        pilot_source, cache / "point_review", live=live, max_sites=len(pilot)
    )
    checkpoint("point_pilot", summary)
    if summary["elevation_ok"] != len(pilot) or summary["climate_ok"] != len(pilot):
        raise RuntimeError("point pilot incomplete; full expansion deferred")
    checkpoint(
        "full_points",
        collect_points(source, cache / "point_review", live=live, max_sites=599),
    )
    initial = collect_lakes(
        source, cache / "lake_review", live=live, limit=5, max_requests=5
    )
    checkpoint("known_lake_pilot", initial)
    if initial["candidate_polygons"] == 5:
        checkpoint(
            "known_lake_recovery",
            collect_lakes(
                source, cache / "lake_review", live=live, limit=24, max_requests=24
            ),
        )
    checkpoint(
        "local_hydrolakes", prepare_lakes(source, cache / "hydrolakes", live=live)
    )
    checkpoint(
        "combined_lakes",
        combine_lakes(
            cache / "lake_review", cache / "hydrolakes", cache / "combined_lakes"
        ),
    )
    stream_pilot = ROOT / "data/habitat_pilots/stream_pilot_sites_v1.csv"
    prepare_rivers(stream_pilot, cache / "hydrorivers", live=live)
    pilot_vectors = cache / "hydrorivers/pilot_nearby_reaches.geojson"
    pilot_vectors.write_bytes(
        (cache / "hydrorivers/nearby_reaches.geojson").read_bytes()
    )
    river = match_rivers(
        stream_pilot, cache / "river_hydrorivers_pilot", vectors=pilot_vectors
    )
    checkpoint("river_pilot", river)
    if river["provisional_vector_matches"]:
        streams = []
        for row in csv_rows(source):
            inference = infer_site_habitat(row["Population.name"], row["Ecotype"])
            if inference.working_waterbody_type == "stream":
                streams.append(
                    {
                        **row,
                        "pilot_class": "stream",
                        "validation_role": (
                            "challenge" if inference.manual_review else "core"
                        ),
                    }
                )
        stream_source = cache / "all_stream_sites.csv"
        write_rows(stream_source, streams, fields + ["pilot_class", "validation_role"])
        prepare_rivers(
            stream_source, cache / "hydrorivers", regions=("eu", "na", "gr"), live=live
        )
        checkpoint(
            "full_rivers",
            match_rivers(
                stream_source,
                cache / "river_hydrorivers_full",
                vectors=cache / "hydrorivers/nearby_reaches.geojson",
                max_sites=len(streams),
            ),
        )
    polygons = cache / "combined_lakes/lake_polygons.geojson"
    shores = collect_shores(
        polygons, cache / "shoreline_local_review", live=live, limit=3, local_dem=True
    )
    checkpoint("shoreline_pilot", shores)
    if any(
        r.get("sources")
        for r in read_json(
            cache / "shoreline_local_review/shoreline_results.json", {}
        ).values()
    ):
        checkpoint(
            "full_shoreline",
            collect_shores(
                polygons,
                cache / "shoreline_local_review",
                live=live,
                limit=len(read_json(polygons, {"features": []})["features"]),
                local_dem=True,
            ),
        )
    summary = build(
        source,
        cache / "point_review/point_data.json",
        cache / "combined_lakes/lake_results.json",
        cache / "river_hydrorivers_full",
        cache / "shoreline_local_review/shoreline_results.json",
        ROOT / "data/derived/pilot_ecological_metrics_v1.csv",
        cache / "full_review_bundle",
    )
    checkpoint("review_bundle", summary)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(json.dumps(run(a.live), indent=2))
