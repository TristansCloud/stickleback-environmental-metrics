"""Exercise local polygon semantics that affect waterbody identity."""
import pytest

shapefile = pytest.importorskip("shapefile")
pytest.importorskip("shapely")
from rasterio.crs import CRS
from scripts.lookup_local_osm_water import lookup


def test_holes_multiple_candidates_and_class_uncertainty(tmp_path):
    path = tmp_path / "water.shp"
    # Shapefile outer rings clockwise, holes counterclockwise.
    outer = [(0, 0), (0, 4), (4, 4), (4, 0), (0, 0)]
    hole = [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]
    with shapefile.Writer(str(path), shapeType=shapefile.POLYGON) as writer:
        for field in ("osm_id", "fclass", "name"):
            writer.field(field, "C", size=100)
        writer.poly([outer, hole]); writer.record("1", "water", "Test Lake")
        writer.poly([outer]); writer.record("2", "reservoir", "Other")
        writer.poly([outer]); writer.record("3", "river", "River")
    path.with_suffix(".prj").write_text(CRS.from_epsg(4326).to_wkt())
    result = lookup(path, .5, .5, "Test Lake")
    assert len(result["features"]) == 2  # Never silently choose an overlap.
    props = result["features"][0]["properties"]
    assert props["waterbody_type"] == "unspecified_water"
    assert props["osm_object_type"] == "unknown"
    assert props["name_evidence"] == "name_agrees"
    assert len(result["features"][0]["geometry"]["coordinates"]) == 2
    inside_hole = lookup(path, 1.5, 1.5)
    assert [f["properties"]["osm_id"] for f in inside_hole["features"]] == ["2"]
    assert lookup(path, 0, .5)["features"][0]["properties"]["point_on_boundary"]
    path.with_suffix(".prj").write_text(CRS.from_epsg(3857).to_wkt())
    with pytest.raises(ValueError, match="EPSG:4326"):
        lookup(path, .5, .5)
