import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from enviro_data.variables.catchment_status import catchment_status
from enviro_data.variables.catchment_area import catchment_area
from enviro_data.variables.sample_elevation import sample_elevation
from enviro_data.variables.catchment_elevation_sd import catchment_elevation_sd
from enviro_data.variables.monthly_catchment_precipitation_volume import monthly_catchment_precipitation_volume
from enviro_data.variables.paved_road_length_density import paved_road_length_density
from enviro_data.variables.road_classification_status import road_classification_status

def test_status_and_null_behavior():
    assert catchment_status(marine=True).status == "not_applicable_marine"
    assert catchment_area(None).area_km2 is None
    assert sample_elevation(-9999, nodata=-9999).elevation_m is None
    assert catchment_elevation_sd([1, 3]).elevation_sd_m == 1

def test_precip_volume_and_roads_are_local_calculations():
    assert monthly_catchment_precipitation_volume(10, 2).volume_m3 == 20000
    roads = [{"length_m": 1000, "surface": "paved", "class": "primary"}, {"length_m": 500, "surface": "gravel", "class": "track"}]
    assert paved_road_length_density(roads, area_km2=2).length_km == 1
    assert road_classification_status(roads).status == "ok"
