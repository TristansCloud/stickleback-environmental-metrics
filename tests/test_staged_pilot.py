from __future__ import annotations

import pytest

from scripts.run_staged_pilot import Metrics, run


def test_stage_guard_rejects_non_pilot_sizes() -> None:
    with pytest.raises(ValueError):
        run(6)


def test_metrics_has_runtime_and_source_counters() -> None:
    metrics = Metrics()
    result = metrics.finish()
    assert result["wall_time_s"] >= 0
    assert result["cpu_time_s"] >= 0
    assert "peak_python_alloc_bytes" in result
    assert set(result["sources"]) == {"copernicus", "earth_engine"}


def test_checked_in_pilot_has_exact_size_and_unique_ids() -> None:
    import csv
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    with (root / "pilot_sites_v1.csv").open(encoding="utf-8-sig", newline="") as handle:
        ids = [row["sample_id"] for row in csv.DictReader(handle)]
    assert len(ids) == len(set(ids)) == 40
