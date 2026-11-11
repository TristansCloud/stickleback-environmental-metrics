"""Build offline provisional stream, marine, and transition development sets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from enviro_data.habitat_pilots import write_habitat_pilots

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "site_overview_v1_clean.csv"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/habitat_pilots")
    parser.add_argument("--core-count", type=int, default=5)
    parser.add_argument("--challenge-count", type=int, default=2)
    args = parser.parse_args()
    print(
        json.dumps(
            write_habitat_pilots(
                args.input,
                args.output_dir,
                core_count=args.core_count,
                challenge_count=args.challenge_count,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
