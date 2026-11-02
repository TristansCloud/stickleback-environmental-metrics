"""Reproducible development cohorts, never reference habitat labels."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .input import EXPECTED_COLUMNS, SiteRecord, load_sites
from .site_habitat import HabitatInference, infer_site_habitat, normalize_site_name

CLASSES = ("stream", "marine", "transition")
VERSION = "provisional-habitat-pilots-v1"
REVIEW_FIELDS = ("reviewed_waterbody_class", "reviewer", "review_notes")


@dataclass(frozen=True)
class Candidate:
    record: SiteRecord
    inference: HabitatInference
    pilot_class: str
    role: str
    selection_basis: str


def candidate_for(record: SiteRecord) -> Candidate | None:
    """Assign one workflow queue; retain conflicts instead of resolving them."""
    inference = infer_site_habitat(record.population_name, record.ecotype)
    domain = record.ecotype
    name_type = inference.name_inferred_waterbody_type
    # Transition evidence takes precedence over its component stream/marine cue.
    if domain == "marine-freshwater" or name_type == "transition":
        kind = "transition"
        clear = domain == "marine-freshwater" and name_type == "transition"
    elif name_type == "stream":
        kind = "stream"
        clear = domain == "freshwater"
    elif domain == "marine":
        kind = "marine"
        clear = name_type == "marine" and not any(
            term in normalize_site_name(record.population_name).split()
            for term in ("slough", "tidal")
        )
    else:
        return None
    clear = (
        clear
        and inference.name_inference_confidence == "high"
        and not inference.manual_review
    )
    role = "core" if clear else "challenge"
    basis = (
        "name_and_ecotype_agree"
        if clear
        else "missing_ambiguous_or_conflicting_name_evidence"
    )
    return Candidate(record, inference, kind, role, basis)


def _distance(a: SiteRecord, b: SiteRecord) -> float:
    """Great-circle angular distance for geographic spread, including dateline."""
    lat_a, lat_b = math.radians(a.latitude), math.radians(b.latitude)
    dlon = math.radians(b.longitude - a.longitude)
    value = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2) ** 2
    )
    return 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def _spread(
    pool: list[Candidate], count: int, anchors: list[Candidate]
) -> list[Candidate]:
    remaining = sorted(pool, key=lambda c: c.record.sample_id)
    selected: list[Candidate] = []
    while len(selected) < count:
        references = anchors + selected
        if references:
            chosen = max(
                remaining,
                key=lambda c: (
                    min(_distance(c.record, other.record) for other in references),
                    c.record.sample_id,
                ),
            )
        else:
            chosen = remaining[0]
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


def select_habitat_pilots(
    records: Iterable[SiteRecord], *, core_count: int = 5, challenge_count: int = 2
) -> tuple[Candidate, ...]:
    """Choose unique named sites per class; never fill shortages with guesses.

    Sort before deduplication so shuffled inputs select the same representative.
    Each name and coordinate pair is used at most once across all cohorts.
    """
    if core_count < 1 or challenge_count < 0:
        raise ValueError("core_count must be positive and challenge_count nonnegative")
    candidates = []
    names, coordinates = set(), set()
    for record in sorted(records, key=lambda r: r.sample_id):
        candidate = candidate_for(record)
        if candidate is None:
            continue
        name = normalize_site_name(record.population_name)
        point = (record.latitude, record.longitude)
        if not name or name in names or point in coordinates:
            continue
        names.add(name)
        coordinates.add(point)
        candidates.append(candidate)
    selected: list[Candidate] = []
    for kind in CLASSES:
        anchors: list[Candidate] = []
        for role, count in (("core", core_count), ("challenge", challenge_count)):
            pool = [c for c in candidates if c.pilot_class == kind and c.role == role]
            if len(pool) < count:
                raise ValueError(
                    f"{kind}/{role}: only {len(pool)} unique candidates for {count} requested"
                )
            chosen = _spread(pool, count, anchors)
            anchors.extend(chosen)
        selected.extend(
            sorted(anchors, key=lambda c: (c.role != "core", c.record.sample_id))
        )
    return tuple(selected)


def _row(candidate: Candidate) -> dict[str, object]:
    record, inference = candidate.record, candidate.inference
    return {
        **dict(
            zip(
                EXPECTED_COLUMNS,
                (
                    record.sample_id,
                    record.population_name,
                    record.population_abbreviation,
                    record.latitude,
                    record.longitude,
                    record.ecotype,
                ),
            )
        ),
        "pilot_class": candidate.pilot_class,
        "validation_role": candidate.role,
        "selection_basis": candidate.selection_basis,
        **asdict(inference),
        "matched_terms": ";".join(inference.matched_terms),
        "classification_status": "provisional_unverified",
        "review_required": True,
        **dict.fromkeys(REVIEW_FIELDS, ""),
    }


def write_habitat_pilots(
    source: str | Path,
    output_dir: str | Path,
    *,
    core_count: int = 5,
    challenge_count: int = 2,
) -> dict[str, object]:
    source, destination = Path(source), Path(output_dir)
    records = load_sites(source, strict=True).records
    selected = select_habitat_pilots(
        records, core_count=core_count, challenge_count=challenge_count
    )
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "selection_version": VERSION,
        "source_file": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_records": len(records),
        "core_per_class": core_count,
        "challenge_per_class": challenge_count,
        "method": "name/ecotype queues; unique normalized names and coordinates; farthest-point great-circle spread; sample_id ties",
        "classification_status": "provisional_unverified",
        "confirmed_labels": 0,
        "cohorts": {},
    }
    for kind in CLASSES:
        rows = [_row(c) for c in selected if c.pilot_class == kind]
        path = destination / f"{kind}_pilot_sites_v1.csv"
        if path.exists():
            with path.open(encoding="utf-8", newline="") as handle:
                if any(
                    any(row.get(field) for field in REVIEW_FIELDS)
                    for row in csv.DictReader(handle)
                ):
                    raise ValueError(
                        f"reviewed file exists: {path}; use a new output directory"
                    )
        manifest["cohorts"][kind] = {
            "file": path.name,
            "sample_ids": [r["sample_id"] for r in rows],
        }
    # Preflight all review files before writing any of them.
    for kind in CLASSES:
        rows = [_row(c) for c in selected if c.pilot_class == kind]
        path = destination / manifest["cohorts"][kind]["file"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(rows[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
        manifest["cohorts"][kind]["sha256"] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    (destination / "selection_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
