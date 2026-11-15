"""Selection/review regressions, not habitat ground-truth tests."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from enviro_data.habitat_pilots import (
    candidate_for,
    select_habitat_pilots,
    write_habitat_pilots,
)
from enviro_data.input import SiteRecord, load_sites

ROOT = Path(__file__).resolve().parents[1]


def record(name, ecotype, sample_id="test"):
    return SiteRecord(sample_id, name, "TEST", 1, 2, ecotype, 2)


def test_conflicts_remain_challenges_and_unknown_freshwater_is_not_guessed():
    river = candidate_for(record("Luga River", "marine"))
    assert (river.pilot_class, river.role) == ("stream", "challenge")
    assert river.inference.working_waterbody_type == "marine"
    transition = candidate_for(record("Vaya River mouth", "freshwater"))
    assert (transition.pilot_class, transition.role) == ("transition", "challenge")
    marine = candidate_for(record("Lake Choboshi", "marine"))
    assert (marine.pilot_class, marine.role) == ("marine", "challenge")
    assert candidate_for(record("Coos Bay Slough", "marine")).role == "challenge"
    assert candidate_for(record("Gifu", "freshwater")) is None
    assert candidate_for(record("Lake Clear", "freshwater")) is None


def test_selection_is_order_independent_unique_and_separates_core_from_conflicts():
    records = load_sites(ROOT / "site_overview_v1_clean.csv", strict=True).records
    selection = select_habitat_pilots(records)
    assert selection == select_habitat_pilots(reversed(records))
    assert len(selection) == len({c.record.sample_id for c in selection}) == 21
    assert len({(c.record.latitude, c.record.longitude) for c in selection}) == 21
    assert Counter((c.pilot_class, c.role) for c in selection) == {
        (kind, role): count
        for kind in ("stream", "marine", "transition")
        for role, count in (("core", 5), ("challenge", 2))
    }
    assert all(not c.inference.manual_review for c in selection if c.role == "core")
    assert all(c.record in records for c in selection)


def test_shortages_fail_without_padding_or_silent_reclassification():
    with pytest.raises(ValueError, match="stream/core"):
        select_habitat_pilots([record("Lake Clear", "freshwater")])
    with pytest.raises(ValueError, match="core_count"):
        select_habitat_pilots([], core_count=0)


def test_regeneration_is_identical_and_cannot_erase_review(tmp_path):
    source = ROOT / "site_overview_v1_clean.csv"
    before = source.read_bytes()
    manifest = write_habitat_pilots(source, tmp_path)
    snapshot = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert write_habitat_pilots(source, tmp_path) == manifest
    assert snapshot == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert source.read_bytes() == before
    assert manifest["confirmed_labels"] == 0
    path = tmp_path / "transition_pilot_sites_v1.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert all(r["classification_status"] == "provisional_unverified" for r in rows)
    assert all(
        r["review_required"] == "True" and r["reviewed_waterbody_class"] == ""
        for r in rows
    )
    rows[0]["reviewed_waterbody_class"] = "estuary"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    reviewed = path.read_bytes()
    with pytest.raises(ValueError, match="reviewed file exists"):
        write_habitat_pilots(source, tmp_path)
    assert path.read_bytes() == reviewed
    for name in (
        "stream_pilot_sites_v1.csv",
        "marine_pilot_sites_v1.csv",
        "selection_manifest.json",
    ):
        assert (tmp_path / name).read_bytes() == snapshot[name]


def test_frozen_cohorts_match_their_manifest_and_original_sites():
    # These cohorts predate later name-inference rules (e.g. Kinugawa).
    # Validate the historical evidence without silently replacing its members.
    directory = ROOT / "data/habitat_pilots"
    manifest = json.loads((directory / "selection_manifest.json").read_text())
    source = ROOT / manifest["source_file"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["source_sha256"]
    originals = {record.sample_id: record for record in load_sites(source, strict=True).records}
    assert len(originals) == manifest["source_records"]
    for kind, cohort in manifest["cohorts"].items():
        path = directory / cohort["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == cohort["sha256"]
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert [row["sample_id"] for row in rows] == cohort["sample_ids"]
        assert Counter(row["validation_role"] for row in rows) == {
            "core": manifest["core_per_class"], "challenge": manifest["challenge_per_class"]}
        for row in rows:
            assert row["pilot_class"] == kind
            original = originals[row["sample_id"]]
            assert row["Population.name"] == original.population_name
            assert row["population.abbreviation"] == original.population_abbreviation
            assert row["Ecotype"] == original.ecotype
            assert float(row["Latitude"]) == original.latitude
            assert float(row["Longitude"]) == original.longitude
