import math

import pytest

from enviro_data.temporal import summarize_temporal
from enviro_data.transforms import apply_source_transform


def test_documented_source_transforms_are_explicit():
    assert math.isclose(apply_source_transform(273.15, "kelvin_to_celsius").value, 0)
    assert apply_source_transform(123, "scale_0.01").value == 1.23
    assert apply_source_transform(35000, "scale_0.001_offset_20").value == 55
    assert apply_source_transform(-0.01, "m_to_mm_nonnegative").status == "invalid_value"
    with pytest.raises(ValueError):
        apply_source_transform(1, "invented")


def test_temporal_summary_retains_extremes_variability_and_missingness():
    result = summarize_temporal([1, 2, None, "bad", 3])
    assert result.mean == 2
    assert result.minimum == 1
    assert result.maximum == 3
    assert result.range == 2
    assert result.valid_count == 3
    assert result.missing_count == 2
    assert result.coefficient_of_variation is not None


def test_temporal_summary_does_not_invent_zero_for_missing_series():
    result = summarize_temporal([None, float("nan")])
    assert result.status == "no_valid_data"
    assert result.mean is None
