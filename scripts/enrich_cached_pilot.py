"""Create analysis-ready ecological metrics from a frozen pilot CSV."""
from __future__ import annotations

import argparse
from pathlib import Path

from enviro_data.cached_enrichment import read_rows, write_enriched_csv


ROOT = Path(__file__).resolve().parents[1]


def latest_cached_pilot() -> Path:
    candidates = sorted((ROOT / "data" / "ee_app_validation").glob("*/pilot_sites.csv"))
    if not candidates:
        raise FileNotFoundError("no frozen pilot_sites.csv bundle is available")
    return candidates[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=ROOT / "data/derived/pilot_ecological_metrics_v1.csv")
    args = parser.parse_args()
    source = args.input or latest_cached_pilot()
    destination = write_enriched_csv(read_rows(source), args.output)
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
