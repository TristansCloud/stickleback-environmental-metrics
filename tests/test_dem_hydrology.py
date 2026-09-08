import hashlib
from pathlib import Path

import pytest

from enviro_data.dem_acquisition import (AcquisitionConfig, CacheFirstAcquirer,
                                         MetadataError, RasterMetadata)
from enviro_data.hydrology import delineate_catchment
from enviro_data.topography import extract_point


class FakeRaster:
    def __init__(self, value):
        self.value = value

    def sample(self, points):
        return [[self.value]]


def metadata(path, *, nodata=-9999, zero_is_ocean_nodata=False):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return RasterMetadata("https://example.invalid/tile.tif", "tile-1", "provider", "2026-01-01T00:00:00Z",
                          digest, "EPSG:4326", "EGM2008", 30, str(path), nodata, zero_is_ocean_nodata)


def test_cache_hit_is_verified_and_network_is_not_called(tmp_path):
    path = tmp_path / "tile.tif"
    path.write_bytes(b"fixture")
    config = AcquisitionConfig(tmp_path, tmp_path / "pilot.csv")
    acquirer = CacheFirstAcquirer(config, fetcher=lambda *_: pytest.fail("network called"))
    acquirer.write_sidecar(metadata(path), path)
    assert acquirer.resolve(metadata(path)) == path


def test_cache_miss_fails_offline(tmp_path):
    path = tmp_path / "missing.tif"
    acquirer = CacheFirstAcquirer(AcquisitionConfig(tmp_path, tmp_path / "pilot.csv"))
    with pytest.raises(FileNotFoundError):
        acquirer.resolve(metadata_for_missing(path))


def metadata_for_missing(path):
    return RasterMetadata("https://example.invalid/tile.tif", "tile-1", "provider", "2026-01-01T00:00:00Z",
                          "0" * 64, "EPSG:4326", "EGM2008", 30, str(path))


def test_nodata_and_ocean_cells_are_null_not_zero(tmp_path):
    path = tmp_path / "tile.tif"
    path.write_bytes(b"fixture")
    assert extract_point(FakeRaster(-9999), metadata(path), 1, 2).elevation_m is None
    assert extract_point(FakeRaster(0), metadata(path, zero_is_ocean_nodata=True), 1, 2).elevation_m is None
    assert extract_point(FakeRaster(-2), metadata(path), 1, 2).elevation_m == -2


def test_metadata_checksum_is_required(tmp_path):
    path = tmp_path / "tile.tif"
    path.write_bytes(b"fixture")
    bad = metadata(path)
    path.write_bytes(b"changed")
    with pytest.raises(MetadataError):
        bad.validate(path)


def test_marine_catchment_requires_explicit_policy():
    result = delineate_catchment(1, 2, ecotype="marine", flow_direction_path="fd", flow_accumulation_path="fa")
    assert result.status == "not_applicable_marine"

    transition = delineate_catchment(1, 2, ecotype="marine-freshwater", flow_direction_path="fd", flow_accumulation_path="fa")
    assert transition.status == "coastal_policy_required"


def test_config_is_bounded_to_40_sites():
    with pytest.raises(ValueError):
        AcquisitionConfig(Path("cache"), Path("pilot.csv"), max_sites=599).validate()
