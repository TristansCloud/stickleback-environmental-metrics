"""Geometry errors here would contaminate lake predictors; use explicit shapes."""
import math

import pytest

from enviro_data.lake_polygons import complete_polygon, contains, full_geometry_query, polygon_metrics, osm_api_geometry
from scripts.run_lake_polygon_pilot import containing_lake_query, evaluate_lake, nearby_lake_query, select_lakes, OverpassUnavailable


def ring(points):
    return [{"lon": x, "lat": y} for x, y in points]


OUTER = ring([(0, 0), (0.01, 0), (0.01, 0.01), (0, 0.01), (0, 0)])
INNER = ring([(0.003, 0.003), (0.006, 0.003), (0.006, 0.006), (0.003, 0.006), (0.003, 0.003)])


def test_whole_geometry_required_and_island_subtracted():
    relation = {"type": "relation", "members": [{"role": "outer", "geometry": OUTER}, {"role": "inner", "geometry": INNER}]}
    polygons = complete_polygon(relation)
    assert contains(polygons, .001, .001)
    assert not contains(polygons, .004, .004)
    area = polygon_metrics(polygons)
    outer_area = polygon_metrics(complete_polygon({"type": "way", "geometry": OUTER}))
    assert 0 < area["lake_area_m2"] < outer_area["lake_area_m2"]
    assert area["lake_perimeter_m"] > outer_area["lake_perimeter_m"]
    assert area["lake_shoreline_development"] > 1


def test_open_or_incomplete_polygon_is_rejected():
    with pytest.raises(ValueError, match="open_or_degenerate"):
        complete_polygon({"type": "way", "geometry": OUTER[:-1]})
    with pytest.raises(ValueError, match="missing_relation_member"):
        complete_polygon({"type": "relation", "members": [{"role": "outer", "geometry": OUTER}, {"role": "inner"}]})
    with pytest.raises(ValueError, match="unclosed_relation"):
        complete_polygon({"type": "relation", "members": [{"role": "outer", "geometry": OUTER[:-1]}]})
    assert "out body geom" in full_geometry_query("way", "123")
    assert "geom(" not in full_geometry_query("way", "123")


def test_fast_discovery_does_not_run_expensive_area_pivot():
    query = nearby_lake_query(66.0, -19.0, 100)
    assert "around:100" in query and "out tags" in query
    assert "is_in" not in query and "pivot" not in query and "out geom" not in query


def test_containment_discovery_does_not_depend_on_shore_distance():
    query = containing_lake_query(64.18656, -21.08836)
    assert "is_in(64.18656,-21.08836)" in query
    assert "pivot.areas" in query and "out tags" in query
    assert "around:" not in query and "out geom" not in query


def test_identify_containing_polygon_before_top_tag_candidate():
    class Client:
        def fetch(self, query, *, stage="unspecified"):
            if "out body geom" in query:
                obj_id = 1 if "id:1" in query else 2
                origin = 3 if obj_id == 1 else 0
                shape = ring([(origin, origin), (origin+.01, origin), (origin+.01, origin+.01), (origin, origin+.01), (origin, origin)])
                return {"elements": [{"type": "way", "id": obj_id, "tags": {"natural": "water", "water": "lake", "name": "Test Lake"}, "geometry": shape}]}, "cache", "cached.json"
            return {"elements": [
                {"type": "way", "id": 1, "tags": {"natural": "water", "water": "lake", "name": "Wrong Lake"}},
                {"type": "way", "id": 2, "tags": {"natural": "water", "water": "lake", "name": "Test Lake"}},
            ]}, "cache", "cached.json"
    row = {"sample_id": "S1", "Population.name": "Test Lake", "Latitude": "0.005", "Longitude": "0.005"}
    result, feature = evaluate_lake(row, Client())
    assert result["osm_id"] == "2" and result["point_inside_polygon"]
    assert result["review_required"] and result["lake_area_m2"] > 0
    assert feature["properties"]["sample_id"] == "S1"


def test_reproducible_40_lake_selection():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "site_overview_v1_clean.csv"
    rows = select_lakes(source)
    assert len(rows) == len({r["sample_id"] for r in rows}) == 40
    assert len({r["Population.name"].casefold() for r in rows}) == 40
    assert all(r["Ecotype"] == "freshwater" for r in rows)


def test_core_osm_api_resolves_nodes_and_rejects_missing_geometry():
    nodes = [{"type": "node", "id": i, **p} for i, p in enumerate(OUTER[:-1], 1)]
    way = {"type": "way", "id": 10, "nodes": [1, 2, 3, 4, 1]}
    relation = {"type": "relation", "id": 20, "members": [{"type": "way", "ref": 10, "role": "outer"}]}
    payload = {"elements": [*nodes, way, relation]}
    poly = complete_polygon(osm_api_geometry(payload, "relation", "20"))
    assert contains(poly, .005, .005)
    assert poly == complete_polygon(osm_api_geometry(payload, "way", "10"))
    with pytest.raises(ValueError, match="missing_osm_api_node"):
        osm_api_geometry({"elements": [*nodes[:-1], way]}, "way", "10")
    with pytest.raises(ValueError, match="missing_osm_api_object_or_member"):
        osm_api_geometry({"elements": [relation]}, "relation", "20")


def test_all_discovery_candidates_survive_geometry_failure(tmp_path):
    import json
    elements = [
        {"type": "way", "id": 1, "tags": {"natural": "water", "water": "lake", "name": "Test Lake"}},
        {"type": "relation", "id": 2, "tags": {"natural": "water", "water": "reservoir", "name": "Neighbour"}},
        {"type": "way", "id": 3, "tags": {"natural": "water", "water": "river"}},
    ]

    class Client:
        def fetch(self, query, *, stage="unspecified"):
            if "out body geom" in query:
                raise OverpassUnavailable("simulated geometry timeout")
            return {"elements": elements}, "cache", "discovery.json"

    log = tmp_path / "candidate_discovery.jsonl"
    row = {"sample_id": "S1", "Population.name": "Test Lake", "Latitude": "0.005", "Longitude": "0.005"}
    result, feature = evaluate_lake(row, Client(), discovery_log=log)
    assert result["status"] == "retrieval_failed" and feature is None
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert [c["osm_id"] for c in entry["candidates"]] == ["1", "2", "3"]
    assert entry["candidates"][1]["tags"]["water"] == "reservoir"
    assert entry["discovery_stage"] == "nearby_500m"
    assert entry["raw_response_cache"] == "discovery.json"
