from pathlib import Path

from enviro_data.input import CRS, EXPECTED_COLUMNS, load_sites


ROOT = Path(__file__).parents[1]


def test_current_clean_input_loads_without_mutation():
    source = ROOT / "site_overview_v1_clean.csv"
    before = source.read_bytes()
    result = load_sites(source, strict=True)
    assert source.read_bytes() == before
    assert len(result.records) == 599
    assert result.diagnostics.rows_read == 599
    assert result.diagnostics.rows_valid == 599
    assert not result.diagnostics.has_errors
    assert result.records[0].crs == CRS
    assert result.records[0].sample_id == "S0001"
    assert result.records[0].latitude == 72.5801


def test_expected_schema_is_explicit():
    assert EXPECTED_COLUMNS == (
        "sample_id", "Population.name", "population.abbreviation",
        "Latitude", "Longitude", "Ecotype",
    )
