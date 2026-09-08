import json
import tempfile
import unittest
from pathlib import Path

from enviro_data.osm_matching import OSMMatcher, OverpassClient


def feature(osm_id, geometry, tags):
    return {"id": f"way/{osm_id}", "geometry": geometry, "tags": tags}


class OSMMatchingTests(unittest.TestCase):
    def test_polygon_has_priority_over_nearby_line(self):
        polygon = feature(10, {"type": "Polygon", "coordinates": [[(-.01, -.01), (.01, -.01), (.01, .01), (-.01, .01), (-.01, -.01)]]}, {"natural": "water", "water": "lake"})
        line = feature(20, {"type": "LineString", "coordinates": [(0, 0), (.02, 0)]}, {"waterway": "stream"})
        result = OSMMatcher([line, polygon]).match("sample-1", 0, 0)
        self.assertEqual((result.osm_id, result.match_method), ("10", "contains_water_polygon"))

    def test_waterway_intersection_is_prioritized(self):
        line = feature(20, {"type": "LineString", "coordinates": [(-.01, 0), (.01, 0)]}, {"waterway": "river"})
        result = OSMMatcher([line], intersect_tolerance_m=2).match("sample-2", 0, 0)
        self.assertEqual(result.match_method, "intersects_waterway")

    def test_ambiguity_and_unmatched(self):
        a = feature(1, {"type": "LineString", "coordinates": [(0, .001), (.001, .001)]}, {"waterway": "stream"})
        b = feature(2, {"type": "LineString", "coordinates": [(0, -.001), (.001, -.001)]}, {"waterway": "stream"})
        self.assertTrue(OSMMatcher([a, b], ambiguity_tolerance_m=2).match("x", 0, 0).review_required)
        self.assertEqual(OSMMatcher([], search_radius_m=10).match("y", 0, 0).match_method, "unmatched")

    def test_overpass_response_is_cached(self):
        calls = []
        def get(*args, **kwargs):
            calls.append(1)
            return type("Response", (), {"raise_for_status": lambda self: None, "json": lambda self: {"elements": [{"type": "way", "id": 7, "tags": {"waterway": "stream"}, "geometry": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": .001}]}]}})()
        with tempfile.TemporaryDirectory() as tmp:
            client = OverpassClient(Path(tmp), http_get=get)
            self.assertEqual(len(client.fetch(0, 0, 100)), 1)
            self.assertEqual(len(client.fetch(0, 0, 100)), 1)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
