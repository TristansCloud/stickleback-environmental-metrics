"""Make a review report from saved pilot outputs, without network access."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def report(run_dir, output):
    with (run_dir / "lake_polygon_pilot.csv").open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    selected = [r for r in rows if r["status"] == "candidate_polygon"]
    statuses = Counter(r["status"] for r in rows)
    classes = Counter(r["osm_waterbody_type"] for r in selected)
    names = Counter(r["name_evidence"] for r in selected)
    discoveries = [json.loads(line) for line in (run_dir / "candidate_discovery.jsonl").read_text(encoding="utf-8").splitlines()]
    unique_candidates = {(event["sample_id"], c["osm_type"], c["osm_id"]) for event in discoveries for c in event["candidates"]}
    artifact_bytes = sum(p.stat().st_size for p in run_dir.rglob("*") if p.is_file())
    requests = [json.loads(line) for line in (run_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    request_stats = {}
    for service in ("overpass", "core_osm"):
        events = [e for e in requests if ("overpass" in e["url"]) == (service == "overpass")]
        failed = [e for e in events if e["status"] == "failed"]
        request_stats[service] = {"attempts": len(events), "failed": len(failed),
                                  "failure_percent": round(100 * len(failed) / len(events), 1) if events else 0,
                                  "successful_response_bytes": sum(e.get("bytes", 0) for e in events),
                                  "http_429": sum("429" in e.get("error", "") for e in failed),
                                  "http_504": sum("504" in e.get("error", "") for e in failed)}
    points = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": row["sample_id"],
         "geometry": {"type": "Point", "coordinates": [float(row["longitude"]), float(row["latitude"])]},
         "properties": {"sample_id": row["sample_id"], "population_name": row["population_name"],
                        "status": row["status"], "review_required": True}}
        for row in rows]}
    (run_dir / "site_coordinates.geojson").write_text(json.dumps(points, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    summary = {"requested": len(metadata["selected_ids"]), "processed": len(rows), "statuses": dict(statuses),
               "candidate_classes": dict(classes), "candidate_name_evidence": dict(names),
               "unique_site_candidate_pairs": len(unique_candidates),
               "network_requests_total_logged": metadata.get("network_requests_total_logged"),
               "request_stats": request_stats,
               "artifact_bytes": artifact_bytes, "pending_ids": metadata["unprocessed_ids"]}
    lines = ["# 40-site OSM lake lookup pilot", "", "Pilot requested October 6, 2026 (Toronto time).", "",
             f"Processed **{len(rows)} of {len(metadata['selected_ids'])} sites**; **{len(selected)}** have a containing candidate polygon.", "",
             f"Statuses: `{dict(statuses)}`. Candidate classes: `{dict(classes)}`.", "",
             f"Name evidence among candidates: `{dict(names)}`.", "",
             f"All discovery logs retain {len(unique_candidates)} distinct site/object pairs, including unselected neighbours.", "",
             f"Logged network attempts: {summary['network_requests_total_logged']}; artifacts occupy approximately {artifact_bytes/1e6:.1f} MB.", "",
             "## Request reliability and server load", "",
             "| Service | Logged attempts | Failed attempts | Failure rate | Successful response bytes |",
             "|---|---:|---:|---:|---:|",
             *[f"| {service} | {s['attempts']} | {s['failed']} | {s['failure_percent']}% | {s['successful_response_bytes']:,} |"
               for service, s in request_stats.items()], "",
             f"Overpass returned {request_stats['overpass']['http_504']} HTTP 504 and {request_stats['overpass']['http_429']} HTTP 429 failures.",
             "Counts include retries and exclude one interrupted attempt that did not finish logging. Successful response bytes exclude error bodies.",
             "This is client reliability evidence, not a measurement of server CPU load. Queries ran sequentially and requested tags only;",
             "full geometry came from bounded reads of known objects through the core API. Request spacing increased from 2 to 5 and finally 10 seconds.",
             "The final retry used a hard 30-second overall request deadline. Rate-limit responses receive at least 30 seconds of cooldown;",
             "the durable client also honors longer Retry-After values across stages, including after the final allowed retry.",
             "Overpass execution slots and cooldowns vary with server load; its broad daily volume guideline does not guarantee availability.",
             "See the [official resource-sharing documentation](https://dev.overpass-api.de/overpass-doc/en/preface/commons.html).", "",
             "## Interpretation", "",
             "These are candidates for manual identity and habitat review. All selected polygons contain the supplied coordinate;",
             "containment does not certify sampling habitat. Lake, pond, reservoir and unspecified water remain separate classes.",
             "Unresolved results retain rejected named polygons and search-limit flags; coordinates were not moved to force matches.",
             "Retrieval failures mean a bounded search was incomplete, not that the waterbody is absent.", "",
             "Area uses a spherical WGS84 approximation and whole-object geometry with island holes subtracted.",
             "Shoreline includes island boundaries. Depth remains pending the thesis equation.", "",
             "## Site results", "", "| Sample | Input name | Status | OSM object | Type | Name evidence | Area km² |",
             "|---|---|---|---|---|---|---:|"]
    for row in rows:
        identity = f"{row['osm_type']}/{row['osm_id']}" if row["osm_id"] else "—"
        link = f"[{identity}](https://www.openstreetmap.org/{identity})" if row["osm_id"] else identity
        area = f"{float(row['lake_area_m2'])/1e6:.6f}" if row["lake_area_m2"] else "—"
        name = row["population_name"].replace("|", "\\|")
        lines.append(f"| {row['sample_id']} | {name} | {row['status']} | {link} | {row['osm_waterbody_type'] or '—'} | {row['name_evidence'] or '—'} | {area} |")
    lines += ["", "## Manual QC queue", ""]
    for row in rows:
        reasons = []
        if row["status"] != "candidate_polygon":
            reasons.append(row["status"])
        if row["status"] == "candidate_polygon" and row["name_evidence"] != "name_agrees":
            reasons.append(row["name_evidence"])
        if row["status"] == "candidate_polygon" and row["osm_waterbody_type"] != "lake":
            reasons.append(f"class={row['osm_waterbody_type']}")
        diagnostics = json.loads(row["diagnostics"])
        if diagnostics.get("candidate_limit_reached"):
            reasons.append("candidate geometry cap; other returned objects remain unevaluated")
        if diagnostics.get("errors"):
            reasons.append("retrieval/geometry errors retained in diagnostics")
        if reasons:
            lines.append(f"- {row['sample_id']} {row['population_name']}: {'; '.join(reasons)}.")
    lines += ["", "All other candidate identities also require manual review. The [manual QC notes](osm_manual_qc.md)",
              "include the South Twin Lake/Wickiup Reservoir border and connectivity question.", "", "## Reproducibility", "",
              f"Pipeline: `{metadata['pipeline_version']}`. Input SHA256: `{metadata['input_sha256']}`.", "",
              f"Evidence folder: `{run_dir.as_posix()}`. It contains the selection manifest, CSV/GeoJSON, all-candidate discovery/outcome",
              "logs, complete evaluated neighbour polygons, request logs, raw response metadata and per-site checkpoints.",
              "`site_coordinates.geojson` supplies the unchanged input points for GIS overlays alongside the candidate polygons.",
              "The successful small trials were imported with their source-cache references; restarting reused completed checkpoints.",
              "Recorded OSM object timestamps identify edits, not retrieval dates. Sources are OSM contributors via Overpass",
              "and the core OSM API, under ODbL attribution requirements.", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    (run_dir / "review_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.run_dir, args.output)))
