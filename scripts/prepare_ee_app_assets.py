"""Prepare local, frozen review artifacts for a future restricted EE App.

This command has no network or Earth Engine code.  It only reads existing pilot
outputs/caches and writes a new versioned bundle under data/ee_app_validation.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from enviro_data.ee_app_assets import prepare_validation_assets

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-json", type=Path, default=ROOT / "data/cache/staged_pilot/stage_40_sites.json")
    parser.add_argument("--osm-matches", type=Path, default=ROOT / "data/osm_pilot/pilot_osm_matches.csv")
    parser.add_argument("--raw-osm-dir", type=Path, default=ROOT / "data/osm_pilot/raw_responses")
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/ee_app_validation")
    args = parser.parse_args()
    print(prepare_validation_assets(args.stage_json, args.osm_matches, args.raw_osm_dir, args.output_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
