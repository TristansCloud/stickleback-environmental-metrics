"""Recover known whole-lake objects and optionally discover other lake sites."""

from __future__ import annotations
import argparse, csv, json, logging, re
from pathlib import Path
from enviro_data.input import load_sites
from enviro_data.lake_lookup import CacheClient, atomic_json, nearby_lake_query, ALLOWED
from enviro_data.lake_polygons import (
    complete_polygon,
    contains,
    name_agreement,
    polygon_metrics,
)
from enviro_data.osm_matching import classify_water_feature, rank_tag_candidates
from enviro_data.site_habitat import infer_site_habitat
from enviro_data.river_sources import sha

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("lake_review")


def known_objects(report):
    return {
        sid: (kind, identity)
        for sid, kind, identity in re.findall(
            r"\| (S\d+) \|[^\n]*?https://www.openstreetmap.org/(way|relation)/(\d+)",
            Path(report).read_text(),
        )
    }


def run(source, output_dir, *, live=False, limit=5, discover=False, max_requests=30):
    records = load_sites(source, strict=True).records
    seeds = known_objects(ROOT / "docs/lake_lookup_40_2026-10-06.md")
    eligible = [
        r
        for r in records
        if infer_site_habitat(r.population_name, r.ecotype).working_waterbody_type
        == "lake"
        and r.ecotype == "freshwater"
        and (discover or r.sample_id in seeds)
    ]
    eligible = sorted(eligible, key=lambda r: (r.sample_id not in seeds, r.sample_id))[
        :limit
    ]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    client = CacheClient(
        out / "raw_responses",
        live=live,
        delay=2,
        timeout=20,
        retries=0,
        max_requests=max_requests,
    )
    results = {}
    features = []
    failures = 0
    for record in eligible:
        dest = out / "checkpoints" / f"{record.sample_id}.json"
        if dest.exists():
            saved = json.loads(dest.read_text())
            if saved["result"]["status"] == "candidate_polygon":
                results[record.sample_id] = saved["result"]
                features.append(saved["feature"])
                continue
        result = {
            "sample_id": record.sample_id,
            "status": "no_candidate",
            "review_required": True,
            "source_ecotype": record.ecotype,
            "original_latitude": record.latitude,
            "original_longitude": record.longitude,
            "candidate_outcomes": [],
        }
        feature = None
        try:
            if record.sample_id in seeds:
                identities = [seeds[record.sample_id]]
                result["discovery_method"] = (
                    "previous_report_object_id; current geometry revalidated"
                )
            else:
                payload, _, cache = client.fetch(
                    nearby_lake_query(record.latitude, record.longitude, 500),
                    stage="lake_nearby_500m",
                )
                candidates = [
                    c
                    for c in rank_tag_candidates(payload["elements"], "lake")
                    if c.feature_class in ALLOWED
                ]
                identities = [(c.osm_type, c.osm_id) for c in candidates[:3]]
                result.update(
                    discovery_method="nearby_500m_tags",
                    discovery_cache=str(cache),
                    discovery_sha256=sha(cache),
                    candidate_limit_reached=len(candidates) > 3,
                )
            matches = []
            for kind, identity in identities:
                obj, retrieval, cache = client.fetch_geometry(
                    kind, identity, stage=f"geometry:{kind}/{identity}"
                )
                polygons = complete_polygon(obj)
                inside = contains(polygons, record.longitude, record.latitude)
                tags = obj.get("tags", {})
                evidence = name_agreement(record.population_name, tags)
                waterclass = classify_water_feature(tags)
                outcome = {
                    "osm_type": kind,
                    "osm_id": identity,
                    "point_inside_polygon": inside,
                    "name_evidence": evidence,
                    "osm_waterbody_type": waterclass,
                    "cache": str(cache),
                    "sha256": sha(cache),
                    "osm_version": obj.get("version"),
                    "osm_timestamp": obj.get("timestamp"),
                    "retrieval": retrieval,
                    "tags": tags,
                }
                result["candidate_outcomes"].append(outcome)
                if inside and waterclass in ALLOWED:
                    geometry = (
                        {"type": "Polygon", "coordinates": polygons[0]}
                        if len(polygons) == 1
                        else {"type": "MultiPolygon", "coordinates": polygons}
                    )
                    matches.append((outcome, polygon_metrics(polygons), geometry))
            if matches:
                matches.sort(key=lambda m: m[0]["name_evidence"] != "name_agrees")
                outcome, metrics, geometry = matches[0]
                result.update(
                    status="candidate_polygon",
                    **outcome,
                    **metrics,
                    ambiguity_flag=len(matches) > 1
                    or result.get("candidate_limit_reached", False),
                )
                feature = {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": dict(result),
                }
            failures = 0
        except Exception as error:
            result.update(
                status="retrieval_or_geometry_failed",
                error=f"{type(error).__name__}: {error}",
            )
            failures += 1
            LOG.warning("lake=%s failed=%s", record.sample_id, error)
        results[record.sample_id] = result
        if feature:
            features.append(feature)
        atomic_json(dest, {"result": result, "feature": feature})
        atomic_json(out / "lake_results.json", results)
        atomic_json(
            out / "lake_polygons.geojson",
            {"type": "FeatureCollection", "features": features},
        )
        LOG.info(
            "lake=%s status=%s progress=%d/%d",
            record.sample_id,
            result["status"],
            len(results),
            len(eligible),
        )
        if failures >= 2 or client.request_count >= max_requests:
            LOG.warning("stopping after repeated failures or request budget")
            break
    atomic_json(out / "lake_results.json", results)
    atomic_json(
        out / "lake_polygons.geojson",
        {"type": "FeatureCollection", "features": features},
    )
    metadata = {
        "source_sha256": sha(source),
        "eligible_selected": len(eligible),
        "processed": len(results),
        "candidate_polygons": len(features),
        "network_requests_this_run": client.request_count,
        "unprocessed_ids": [
            r.sample_id for r in eligible if r.sample_id not in results
        ],
        "area_method": "spherical WGS84; complete geometry; holes subtracted",
        "shoreline_method": "great-circle ring segments including island shores; unsimplified raw geometry",
    }
    atomic_json(out / "run_metadata.json", metadata)
    return metadata


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ROOT / "site_overview_v1_clean.csv")
    p.add_argument("--output-dir", type=Path, default=ROOT / "data/cache/lake_review")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--max-requests", type=int, default=30)
    p.add_argument("--live", action="store_true")
    p.add_argument("--discover", action="store_true")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(
        json.dumps(
            run(
                a.input,
                a.output_dir,
                live=a.live,
                limit=a.limit,
                discover=a.discover,
                max_requests=a.max_requests,
            ),
            indent=2,
        )
    )
