"""Overall deadline and HTTP status propagation; no live network requests."""
import base64
import json
import subprocess
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from enviro_data import osm_http


def test_deadline_terminates_worker_and_reports_failure(monkeypatch):
    def stalled(command, **kwargs):
        assert kwargs["timeout"] == 3
        raise subprocess.TimeoutExpired(command, 3)
    monkeypatch.setattr(osm_http.subprocess, "run", stalled)
    with pytest.raises(URLError, match="overall_request_deadline_exceeded"):
        osm_http.bounded_urlopen(Request("https://example.test/"), timeout=3)


def test_worker_preserves_post_body_and_throttle_headers(monkeypatch):
    def reply(command, **kwargs):
        message = json.loads(kwargs["input"])
        assert base64.b64decode(message["data"]) == b"data=query"
        return SimpleNamespace(returncode=0, stdout=b'{"http_error":429,"error":"throttled","headers":{"Retry-After":"30"}}')
    monkeypatch.setattr(osm_http.subprocess, "run", reply)
    with pytest.raises(HTTPError) as error:
        osm_http.bounded_urlopen(Request("https://example.test/", data=b"data=query"))
    assert error.value.code == 429 and error.value.headers["Retry-After"] == "30"
