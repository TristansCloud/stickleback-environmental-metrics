"""Build the full review bundle from immutable input and available cached evidence."""

import argparse, json
from pathlib import Path
from enviro_data.review_dataset import build

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output-dir", type=Path, default=ROOT / "data/cache/full_review_bundle"
    )
    a = p.parse_args()
    print(
        json.dumps(
            build(
                ROOT / "site_overview_v1_clean.csv",
                ROOT / "data/cache/point_review/point_data.json",
                ROOT / "data/cache/combined_lakes/lake_results.json",
                ROOT / "data/cache/river_hydrorivers_full",
                ROOT / "data/cache/shoreline_local_review/shoreline_results.json",
                ROOT / "data/derived/pilot_ecological_metrics_v1.csv",
                a.output_dir,
            ),
            indent=2,
        )
    )
