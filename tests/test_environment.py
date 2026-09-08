import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from enviro_data.climate import ClimateExtractor
from enviro_data.terrain import TerrainExtractor, CatchmentStatus

class FakeRaster:
    def __init__(self, value, nodata=-9999):
        self.value, self.nodata, self.crs = value, nodata, "EPSG:4326"
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def sample(self, points): return [[self.value]]

def opener(path):
    if "missing" in path: raise FileNotFoundError(path)
    return FakeRaster(-9999 if "nodata" in path else 12)

def test_marine_climate_is_explicitly_null():
    result = ClimateExtractor({1: {"tmin": "x.tif"}}, opener).extract(70, 20, ecotype="marine")
    assert result.status == "not_applicable_marine"
    assert result.months[0].tmin is None
    assert result.months[0].status == "not_applicable_marine"

def test_local_raster_values_and_provenance():
    result = ClimateExtractor({1: {"tmin": "a.tif", "tmax": "b.tif", "precip": "c.tif"}}, opener).extract(1, 2)
    row = result.months[0]
    assert (row.tmin, row.tmax, row.precip) == (12.0, 12.0, 12.0)
    assert row.provenance[0].path == "a.tif"
    assert result.months[1].status == "no_valid_data"

def test_nodata_is_null_not_zero_and_catchment_is_stub():
    summary = TerrainExtractor(opener).summary("nodata.tif", 1, 2)
    assert summary.elevation is None
    assert summary.status == "no_valid_dem_data"
    catchment = TerrainExtractor(opener).delineate_catchment(1, 2)
    assert catchment.status == CatchmentStatus.NOT_IMPLEMENTED
    assert catchment.area_km2 is None

