import unittest
from enviro_data.osm_matching import OSMCandidate, OSMMatch
from enviro_data.variables import *

POLY = {"type": "Polygon", "coordinates": [[(-.01, -.01), (.01, -.01), (.01, .01), (-.01, .01), (-.01, -.01)]]}
LINE = {"type": "LineString", "coordinates": [(0, 0), (.01, 0)]}

class OSMVariableTests(unittest.TestCase):
    def test_identity_and_polygon_metrics(self):
        match = OSMMatch("s", "way-1", {"natural": "water"}, "lake", "contains_water_polygon")
        candidate = OSMCandidate("way-1", POLY, {"natural": "water"}, "lake")
        self.assertEqual(compute_water_feature_identity(match).value["osm_id"], "way-1")
        self.assertGreater(compute_water_surface_area(candidate).value, 0)
        self.assertGreater(compute_water_perimeter(candidate).value, 0)
        self.assertGreater(compute_shoreline_development(candidate).value, 0)

    def test_waterway_and_explicit_unavailable_stream_order(self):
        candidate = OSMCandidate("way-2", LINE, {"waterway": "stream"}, "stream")
        self.assertEqual(compute_waterway_class(candidate).value, "stream")
        self.assertGreater(compute_waterway_length(candidate).value, 0)
        result = compute_stream_order(candidate)
        self.assertIsNone(result.value); self.assertEqual(result.status, "unavailable")
        self.assertEqual(compute_stream_order(candidate, {"way-2": 3}).value, 3)

    def test_coast_distance_and_context_are_offline(self):
        coast = OSMCandidate("coast-1", {"type": "LineString", "coordinates": [(0, 0), (.01, 0)]}, {"natural": "coastline"}, "coastline")
        distance = compute_distance_to_coast((.005, .001), [coast])
        self.assertGreater(distance.value, 0)
        self.assertTrue(compute_coastal_context((.005, .001), [coast], threshold_m=200).value["within_threshold"])

if __name__ == "__main__": unittest.main()
