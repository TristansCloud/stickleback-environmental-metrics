from collections import Counter
from pathlib import Path

from enviro_data.input import load_sites
from enviro_data.pilot import PilotConfig, select_pilot, write_pilot_csv
from enviro_data.runner import run_pilot


ROOT = Path(__file__).parents[1]


def test_pilot_is_exact_and_stratified():
    records = load_sites(ROOT / "site_overview_v1_clean.csv", strict=True).records
    pilot = select_pilot(records)
    assert len(pilot) == 40
    assert len({x.sample_id for x in pilot}) == 40
    assert Counter(x.ecotype for x in pilot) == {"freshwater": 33, "marine": 6, "marine-freshwater": 1}
    assert [x.sample_id for x in pilot] == sorted(x.sample_id for x in pilot)


def test_runner_is_offline_by_default_and_artifact_round_trips(tmp_path):
    result = run_pilot(ROOT / "site_overview_v1_clean.csv")
    assert len(result.records) == 40
    assert result.network_enabled is False
    assert result.variables == tuple({"sample_id": record.sample_id} for record in result.records)
    out = tmp_path / "pilot.csv"
    write_pilot_csv(result.records, out)
    loaded = load_sites(out, strict=True)
    assert tuple(x.sample_id for x in loaded.records) == tuple(x.sample_id for x in result.records)
