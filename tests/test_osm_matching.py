import json
import tempfile
import unittest
from pathlib import Path

from enviro_data.osm_matching import (
    OSMCandidate,
    OSMMatcher,
    OverpassClient,
    build_habitat_overpass_query,
    build_overpass_query,
    build_ranked_geometry_query,
    match_ranked_tags,
    overpass_element_to_feature,
    rank_tag_candidates,
)


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

    def test_query_includes_enclosing_areas_relations_and_coastline(self):
        query = build_overpass_query(50, -120, 3000, 10000)
        self.assertIn("is_in(50,-120)", query)
        self.assertIn("rel(pivot.areas)[natural=water]", query)
        self.assertIn("rel(around:3000,50,-120)[natural=water]", query)
        self.assertIn("way(around:10000,50,-120)[natural=coastline]", query)

    def test_habitat_queries_avoid_irrelevant_feature_families(self):
        lake = build_habitat_overpass_query(50, -120, 1000, "lake")
        marine = build_habitat_overpass_query(50, -120, 3000, "marine")
        self.assertIn("is_in(50,-120)", lake)
        self.assertNotIn("natural=coastline", lake)
        self.assertNotIn("is_in", marine)
        self.assertIn("natural=coastline", marine)
        self.assertIn("[waterway]", marine)
        self.assertIn("natural=wetland", marine)
        self.assertTrue(marine.endswith("out tags;"))
        self.assertNotIn("out geom", marine)
        self.assertNotIn("is_in", build_habitat_overpass_query(50, -120, 250, "stream"))
        self.assertNotIn("is_in", build_habitat_overpass_query(50, -120, 500, "unknown"))

    def test_tag_candidates_are_ranked_for_habitat_without_geometry(self):
        elements = [
            {"type": "way", "id": 30, "tags": {"natural": "wetland"}},
            {"type": "way", "id": 20, "tags": {"waterway": "stream"}},
            {"type": "relation", "id": 10, "tags": {"natural": "bay", "name": "Estuary"}},
        ]
        ranked = rank_tag_candidates(elements, "marine")
        self.assertEqual([(x.osm_type, x.osm_id, x.feature_class) for x in ranked], [
            ("relation", "10", "bay"),
            ("way", "20", "stream"),
            ("way", "30", "wetland"),
        ])
        match = match_ranked_tags("site", ranked, "marine", 500)
        self.assertEqual((match.osm_id, match.match_method, match.distance_m), ("10", "ranked_tags_within_radius", None))

    def test_ranked_geometry_query_targets_one_feature_and_clips_output(self):
        query = build_ranked_geometry_query("way", "123", 64.71699, 177.50497, 500)
        self.assertIn("way(id:123)", query)
        self.assertIn("out geom(", query)
        self.assertIn(") tags;", query)

    def test_relation_member_geometries_are_stitched(self):
        relation = {
            "type": "relation",
            "id": 99,
            "tags": {"type": "multipolygon", "natural": "water", "water": "lake"},
            "members": [
                {"role": "outer", "geometry": [{"lon": -1, "lat": -1}, {"lon": 1, "lat": -1}, {"lon": 1, "lat": 1}]},
                {"role": "outer", "geometry": [{"lon": 1, "lat": 1}, {"lon": -1, "lat": 1}, {"lon": -1, "lat": -1}]},
            ],
        }
        candidate = OSMCandidate.from_feature(overpass_element_to_feature(relation))
        result = OSMMatcher([candidate]).match("site", 0, 0, "lake")
        self.assertEqual(result.match_method, "contains_water_polygon")
        self.assertEqual(candidate.osm_type, "relation")

    def test_multipolygon_holes_are_not_treated_as_water(self):
        geometry = {"type": "MultiPolygon", "coordinates": [
            [[(-2, -2), (2, -2), (2, 2), (-2, 2), (-2, -2)], [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5), (-.5, -.5)]],
            [[(3, 3), (4, 3), (4, 4), (3, 4), (3, 3)]],
        ]}
        candidate = OSMCandidate.from_feature(feature(50, geometry, {"natural": "water", "water": "lake"}))
        self.assertNotEqual(OSMMatcher([candidate], search_radius_m=10).match("hole", 0, 0).match_method, "contains_water_polygon")

    def test_expected_type_guides_nearest_candidate(self):
        stream = feature(1, {"type": "LineString", "coordinates": [(0, .0001), (.01, .0001)]}, {"waterway": "stream"})
        lake = feature(2, {"type": "Polygon", "coordinates": [[(-.01, .001), (.01, .001), (.01, .01), (-.01, .01), (-.01, .001)]]}, {"natural": "water", "water": "lake"})
        result = OSMMatcher([stream, lake], search_radius_m=2000).match("lake-site", 0, 0, "lake")
        self.assertEqual(result.osm_id, "2")


if __name__ == "__main__":
    unittest.main()
