import pytest
from enviro_data.point_sources import MONTHS, parse_climate, elevation_batch


def payload():
    return {
        "header": {"fill_value": -999, "range": "test period"},
        "parameters": {"T2M": {"units": "C"}, "PRECTOTCORR": {"units": "mm/day"}},
        "properties": {
            "parameter": {
                "T2M": {**{m: i for i, m in enumerate(MONTHS)}, "ANN": 5.5},
                "PRECTOTCORR": {**{m: 0 for m in MONTHS}, "ANN": 0},
            }
        },
    }


def test_climate_units_period_missingness():
    p = payload()
    r = parse_climate(p)
    assert (
        r["climate_status"] == "ok" and r["monthly_mean_air_temperature_range_c"] == 11
    )
    assert (
        r["annual_mean_precipitation_mm_day"] == 0
        and r["climate_period"] == "test period"
    )
    p["properties"]["parameter"]["T2M"]["JAN"] = -999
    assert parse_climate(p)["coldest_month_mean_air_temperature_c"] is None
    assert parse_climate(p)["climate_status"] == "partial_or_missing"
    p["parameters"]["PRECTOTCORR"]["units"] = "mm"
    with pytest.raises(ValueError, match="units"):
        parse_climate(p)


def test_elevation_length_mismatch_and_real_zero(monkeypatch, tmp_path):
    import enviro_data.point_sources as sources

    monkeypatch.setattr(
        sources, "fetch_json", lambda *a, **k: ({"elevation": [0, None]}, {})
    )
    values, _ = elevation_batch([(0, 0), (1, 1)], tmp_path)
    assert values == [0, None]
    with pytest.raises(ValueError, match="length"):
        elevation_batch([(0, 0)], tmp_path)
