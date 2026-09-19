"""Create an auditable habitat-inference copy of the immutable 40-site pilot."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from enviro_data.site_habitat import infer_site_habitat

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "pilot_sites_v1.csv"
DEFAULT_OUTPUT = ROOT / "data" / "derived" / "pilot_sites_with_name_habitat_v1.csv"


def run(input_csv: Path = DEFAULT_INPUT, output_csv: Path = DEFAULT_OUTPUT) -> list[dict[str, object]]:
    with input_csv.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 40:
        raise ValueError(f"expected exactly 40 pilot records, found {len(rows)}")

    output_rows: list[dict[str, object]] = []
    for row in rows:
        inference = infer_site_habitat(row["Population.name"], row["Ecotype"])
        output_rows.append(
            {
                **row,
                "name_inferred_waterbody_type": inference.name_inferred_waterbody_type,
                "name_inference_matched_terms": ";".join(inference.matched_terms),
                "name_inference_confidence": inference.name_inference_confidence,
                "working_waterbody_type": inference.working_waterbody_type,
                "working_type_basis": inference.working_type_basis,
                "habitat_manual_review": inference.manual_review,
            }
        )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    return output_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inferred = run(args.input, args.output)
    from collections import Counter

    print(Counter(row["working_waterbody_type"] for row in inferred))
