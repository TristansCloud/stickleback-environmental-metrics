"""Sample provisional shoreline elevation profiles from recovered lake geometry."""

import argparse, json, logging
from pathlib import Path
from enviro_data.lake_lookup import atomic_json
from enviro_data.point_sources import elevation_batch
from enviro_data.shoreline import sample_plan, summarize
from enviro_data.river_sources import sha

ROOT = Path(__file__).resolve().parents[1]


def run(polygons, output_dir, *, live=False, limit=3, local_dem=False, ring_count=200):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    features = json.loads(Path(polygons).read_text())["features"][:limit]
    results = {}
    failures = 0
    for feature in features:
        sid = feature["properties"]["sample_id"]
        dest = out / f"{sid}.json"
        identity = (
            __import__("hashlib")
            .sha256(json.dumps({"feature": feature, "sampling_version": 2, "surface_count": 12, "ring_count": ring_count}, sort_keys=True).encode())
            .hexdigest()
        )
        if dest.exists():
            prior = json.loads(dest.read_text())
            if prior.get("geometry_sha256") == identity and prior["status"] not in {
                "retrieval_failed"
            }:
                results[sid] = prior
                continue
        try:
            plan = sample_plan(feature["geometry"], ring_count=ring_count)
            coordinates = [p for group in plan["groups"].values() for p in group]
            if local_dem:
                from enviro_data.local_dem import sample_coordinates

                elevations, sources = sample_coordinates(
                    coordinates, out.parent / "copernicus90_tiles", live=live
                )
            else:
                elevations = []
                sources = []
                for i in range(0, len(coordinates), 100):
                    values, source = elevation_batch(
                        coordinates[i : i + 100], out / "raw_responses", live=live
                    )
                    elevations.extend(values)
                    sources.append(source)
            result = {
                **summarize(plan, elevations),
                "sample_id": sid,
                "geometry_sha256": identity,
                "plan": plan,
                "sample_elevations_m": elevations,
                "sources": sources,
                "review_required": True,
            }
            failures = 0
        except ValueError as error:
            result = {
                "sample_id": sid,
                "status": "unsupported_geometry_or_sampling",
                "error": str(error),
                "geometry_sha256": identity,
            }
            failures = 0
        except Exception as error:
            result = {
                "sample_id": sid,
                "status": "retrieval_failed",
                "error": str(error),
                "geometry_sha256": identity,
            }
            failures += 1
        atomic_json(dest, result)
        results[sid] = result
        logging.info("shoreline sample=%s status=%s", sid, result["status"])
        if failures >= 2:
            break
    atomic_json(out / "shoreline_results.json", results)
    return {
        "processed": len(results),
        "statuses": {
            status: sum(r["status"] == status for r in results.values())
            for status in {r["status"] for r in results.values()}
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--polygons",
        type=Path,
        default=ROOT / "data/cache/lake_review/lake_polygons.geojson",
    )
    p.add_argument(
        "--output-dir", type=Path, default=ROOT / "data/cache/shoreline_review"
    )
    p.add_argument("--limit", type=int, default=3)
    p.add_argument("--ring-count", type=int, default=200, help="Maximum deterministic sample points per land-side band")
    p.add_argument("--live", action="store_true")
    p.add_argument("--local-dem", action="store_true")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(
        json.dumps(
            run(
                a.polygons,
                a.output_dir,
                live=a.live,
                limit=a.limit,
                local_dem=a.local_dem,
                ring_count=a.ring_count,
            ),
            indent=2,
        )
    )
