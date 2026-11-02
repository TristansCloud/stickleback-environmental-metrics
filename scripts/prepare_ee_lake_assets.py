"""Prepare frozen lake-review GeoJSON collections without network requests."""
import argparse
from pathlib import Path

from enviro_data.ee_lake_assets import prepare_lake_validation_assets


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/ee_app_validation"))
    args = parser.parse_args()
    print(prepare_lake_validation_assets(args.run_dir, args.output_root))


if __name__ == "__main__":
    main()
