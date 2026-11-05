"""Generate provisional habitat labels without editing the original review table."""
import argparse
from collections import Counter
import csv
from pathlib import Path

from enviro_data.site_habitat import infer_site_habitat


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--output", type=Path, default=Path("sites_multilingual.csv"))
    args=parser.parse_args()
    original=args.repo/"data/ee_full_review/source_2026-11-01/stickleback_full_review_v1.csv"
    with original.open(encoding="utf-8-sig",newline="") as file:
        rows=list(csv.DictReader(file))
    with (args.repo/"data/habitat_name_evidence.csv").open(encoding="utf-8",newline="") as file:
        evidence={r["sample_id"]:r for r in csv.DictReader(file)}
    changed=[]
    for row in rows:
        row["habitat_evidence_url"]=""
        if row["working_waterbody_type"]!="unknown":
            continue
        reference=evidence.get(row["sample_id"])
        inferred=infer_site_habitat(row["population_name"],row["source_ecotype"])
        if reference:
            if reference["population_name"]!=row["population_name"] or row["source_ecotype"]!="freshwater":
                raise ValueError(f"Habitat reference differs from input: {row['sample_id']}")
            row["working_waterbody_type"]=reference["working_waterbody_type"]
            row["working_type_basis"]=reference.get("evidence_basis") or "documented_place_name"
            row["name_inferred_waterbody_type"]=reference["working_waterbody_type"]
            row["habitat_evidence_url"]=reference["evidence_url"]
            row["name_inference_confidence"]="reference"
            row["matched_terms"]=""
        elif inferred.working_waterbody_type!="unknown":
            row["working_waterbody_type"]=inferred.working_waterbody_type
            row["working_type_basis"]="provisional_multilingual_name_evidence"
            row["name_inferred_waterbody_type"]=inferred.name_inferred_waterbody_type
            row["matched_terms"]=";".join(inferred.matched_terms)
            row["name_inference_confidence"]=inferred.name_inference_confidence
        else:
            continue
        row["review_required"]="True"
        row["classification_status"]="provisional_unverified"
        changed.append(row)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",encoding="utf-8-sig",newline="") as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("Changed",len(changed),Counter(r["working_waterbody_type"] for r in changed),flush=True)
    print("Current classes",Counter(r["working_waterbody_type"] for r in rows),flush=True)


if __name__=="__main__":
    main()
