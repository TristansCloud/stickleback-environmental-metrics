"""Build frozen full-dataset Earth Engine collections; no network or sampling."""
import argparse
from pathlib import Path
from enviro_data.ee_full_review import prepare_full_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="Extracted portable review ZIP")
    parser.add_argument("--output-root", type=Path, default=Path("data/ee_full_review"))
    args = parser.parse_args()
    print(prepare_full_review(args.bundle, args.output_root))


if __name__ == "__main__":
    main()
