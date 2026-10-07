"""Reproducible, resumable 40-site hybrid OSM water polygon pilot.

Offline by default. Coordinates discover ID/tags through Overpass; complete
geometry comes from the core OSM API. Every result still needs identity review.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

from enviro_data.lake_lookup import (CacheClient, ENDPOINT, OverpassUnavailable, containing_lake_query,
                                    evaluate_lake, nearby_lake_query, record_discovery, run_sites)
from enviro_data.site_habitat import infer_site_habitat, normalize_site_name

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "site_overview_v1_clean.csv"


def select_lakes(source: Path, count: int = 40):
    if count < 1:
        raise ValueError("count must be positive")
    with source.open(encoding="utf-8-sig", newline="") as file:
        records = list(csv.DictReader(file))
    eligible, used_names = [], set()
    for row in records:
        inference = infer_site_habitat(row["Population.name"], row["Ecotype"])
        name = normalize_site_name(row["Population.name"])
        if (inference.working_waterbody_type != "lake" or row["Ecotype"].strip().lower() != "freshwater"
                or inference.name_inference_confidence != "high" or not name or name in used_names):
            continue
        eligible.append(row)
        used_names.add(name)
    if len(eligible) < count:
        raise ValueError(f"only {len(eligible)} eligible named lake sites for {count} requested")
    eligible.sort(key=lambda r: (float(r["Latitude"]), r["sample_id"]))
    return [eligible[(i * len(eligible) + len(eligible) // 2) // count] for i in range(count)]


def run(source=DEFAULT_INPUT, output_dir=ROOT / "data/lake_pilot", *, live=False, count=40, sample_id=None,
        delay=2., timeout=30., max_failures=3, endpoint=ENDPOINT, retries=1,
        max_requests=320, max_candidates=3, resume=True):
    rows = select_lakes(source, count)
    if sample_id is not None:
        rows = [row for row in rows if row["sample_id"] == sample_id]
        if not rows:
            raise ValueError(f"sample_id {sample_id!r} is not in the selected pilot")
    return run_sites(rows, source, output_dir, live=live, delay=delay, timeout=timeout,
                     max_failures=max_failures, endpoint=endpoint, retries=retries,
                     max_requests=max_requests, max_candidates=max_candidates, resume=resume)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/lake_pilot")
    parser.add_argument("--live-osm", action="store_true")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--sample-id", help="Run one ID from the deterministic selection")
    parser.add_argument("--request-delay-seconds", type=float, default=2.)
    parser.add_argument("--timeout-seconds", type=float, default=30.)
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--retries", type=int, default=1, help="Retries after the initial request")
    parser.add_argument("--max-requests", type=int, default=320)
    parser.add_argument("--max-failures", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=3, help="Geometry reads per discovery stage")
    parser.add_argument("--no-resume", action="store_true", help="Reevaluate sites using existing raw caches")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = run(args.input, args.output_dir, live=args.live_osm, count=args.count, sample_id=args.sample_id,
                  delay=args.request_delay_seconds, timeout=args.timeout_seconds, endpoint=args.endpoint,
                  retries=args.retries, max_requests=args.max_requests, max_failures=args.max_failures,
                  max_candidates=args.max_candidates, resume=not args.no_resume)
    print(json.dumps({"processed": len(results), "status_counts": {status: sum(r["status"] == status for r in results)
                      for status in sorted({r["status"] for r in results})}}))
