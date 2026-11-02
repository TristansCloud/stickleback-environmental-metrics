"""Network failure and checkpoint tests for the bounded hybrid pilot."""
import io
import json
from urllib.error import HTTPError

import pytest

from enviro_data import lake_lookup as lookup

ROW = {"sample_id": "S1", "Population.name": "Test Lake", "Latitude": "0.005", "Longitude": "0.005"}
OBJ = {"type": "way", "id": 1, "tags": {"name": "Test Lake", "natural": "water", "water": "lake"},
       "geometry": [{"lon": x, "lat": y} for x, y in [(0, 0), (.01, 0), (.01, .01), (0, .01), (0, 0)]]}


def test_transient_retry_cache_and_endpoint_isolation(monkeypatch, tmp_path):
    calls = []

    def respond(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 504, "timeout", {}, None)
        return io.BytesIO(json.dumps({"elements": []}).encode())

    monkeypatch.setattr(lookup, "urlopen", respond)
    monkeypatch.setattr(lookup.time, "sleep", lambda delay: None)
    client = lookup.CacheClient(tmp_path / "raw", live=True, delay=0)
    assert client.fetch("query")[1] == "network"
    assert client.fetch("query")[1] == "cache"
    assert len(calls) == 2
    assert client.cache_path("https://a.test", b"query") != client.cache_path("https://b.test", b"query")
    records = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text().splitlines()]
    assert [r["status"] for r in records] == ["failed", "ok"]


def test_overpass_remark_is_failure_not_empty_success(monkeypatch, tmp_path):
    monkeypatch.setattr(lookup, "urlopen", lambda *a, **k: io.BytesIO(b'{"elements": [], "remark": "runtime error: timeout"}'))
    client = lookup.CacheClient(tmp_path, live=True, retries=0)
    with pytest.raises(lookup.OverpassUnavailable, match="overpass_remark"):
        client.fetch("query")
    assert not client.cache_path(client.endpoint, b"data=query").exists()


def test_throttling_has_long_backoff(monkeypatch, tmp_path):
    calls, waits = [], []

    def respond(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 429, "throttled", {}, None)
        return io.BytesIO(b'{"elements": []}')

    monkeypatch.setattr(lookup, "urlopen", respond)
    monkeypatch.setattr(lookup.time, "sleep", waits.append)
    client = lookup.CacheClient(tmp_path, live=True, delay=0)
    client.fetch("query")
    assert 30 in waits and len(calls) == 2


def test_final_429_preserves_server_cooldown_for_next_stage(monkeypatch, tmp_path):
    clock, calls, waits = [0.0], [], []

    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    def respond(request, timeout):
        calls.append(clock[0])
        if len(calls) == 1:
            raise HTTPError(request.full_url, 429, "throttled", {"Retry-After": "90"}, None)
        return io.BytesIO(b'{"elements": []}')

    monkeypatch.setattr(lookup.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(lookup.time, "sleep", sleep)
    monkeypatch.setattr(lookup, "urlopen", respond)
    client = lookup.CacheClient(tmp_path, live=True, delay=10, retries=0)
    with pytest.raises(lookup.OverpassUnavailable):
        client.fetch("first")
    client.fetch("next stage")
    assert calls == [0, 90]
    assert max(waits) <= 60


def test_discovery_failure_falls_back_without_overpass_geometry():
    class Client:
        live = True

        def fetch(self, query, *, stage):
            if stage == "nearby_500m":
                raise lookup.OverpassUnavailable("temporary timeout")
            assert "out tags" in query
            return {"elements": [OBJ]}, "cache", "discovery.json"

        def fetch_geometry(self, osm_type, osm_id, *, stage):
            assert (osm_type, osm_id) == ("way", "1")
            return OBJ, "cache", "core.json"

    result, feature = lookup.evaluate_lake(ROW, Client())
    assert result["status"] == "candidate_polygon"
    assert result["discovery_stage"] == "containing_area"
    assert result["geometry_api"] == "core_osm"
    assert result["ambiguity_flag"] is True
    assert feature["properties"]["osm_waterbody_type"] == "lake"


def test_checkpoint_resume_and_input_mismatch(monkeypatch, tmp_path):
    calls = []

    class Client:
        live = False
        request_count = 0

        def __init__(self, *args):
            pass

        def fetch(self, query, *, stage):
            calls.append(stage)
            return {"elements": [OBJ]}, "cache", "discovery.json"

        def fetch_geometry(self, *args, **kwargs):
            return OBJ, "cache", "core.json"

    monkeypatch.setattr(lookup, "CacheClient", Client)
    source = tmp_path / "input.csv"
    source.write_text("immutable input")
    output = tmp_path / "run"
    first = lookup.run_sites([ROW], source, output)
    assert first[0]["status"] == "candidate_polygon"
    assert len(calls) == 1
    second = lookup.run_sites([ROW], source, output)
    assert second == first and len(calls) == 1
    assert json.loads((output / "run_metadata.json").read_text())["unprocessed_ids"] == []
    source.write_text("changed input")
    with pytest.raises(ValueError, match="manifest differs"):
        lookup.run_sites([ROW], source, output)


def test_core_tags_and_failed_competitors_are_retained(tmp_path):
    class Client:
        live = True

        def fetch(self, query, *, stage):
            return {"elements": [OBJ, {**OBJ, "id": 2}, {**OBJ, "id": 3}]}, "cache", "discovery.json"

        def fetch_geometry(self, osm_type, osm_id, *, stage):
            if osm_id == "1":
                raise lookup.OverpassUnavailable("object read failed")
            if osm_id == "2":
                # Fresh core API tags disagree with earlier discovery tags.
                return {**OBJ, "id": 2, "tags": {"natural": "water", "water": "river"}}, "cache", "river.json"
            return {**OBJ, "id": 3}, "cache", "lake.json"

    audit = tmp_path / "outcomes.jsonl"
    result, feature = lookup.evaluate_lake(ROW, Client(), candidate_log=audit, candidate_dir=tmp_path / "polygons")
    assert result["osm_id"] == "3" and result["ambiguity_flag"] is True
    assert result["osm_waterbody_type"] == "lake"
    outcomes = [json.loads(line) for line in audit.read_text().splitlines()]
    assert [x["status"] for x in outcomes] == ["retrieval_failed", "current_tags_excluded", "containing_candidate"]
    assert (tmp_path / "polygons/S1_way_2.geojson").exists()
    assert feature["properties"]["review_required"] is True
