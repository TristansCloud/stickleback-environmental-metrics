"""Hard overall deadline for read-only OSM HTTP requests, including slow headers.

urllib's socket timeout is not a total request deadline. A short-lived worker
lets the parent terminate a stalled connection on Windows without leaked threads.
"""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen as native_urlopen


def bounded_urlopen(request, timeout=30):
    message = {"url": request.full_url, "data": base64.b64encode(request.data).decode() if request.data is not None else None,
               "headers": dict(request.header_items()), "timeout": timeout}
    try:
        result = subprocess.run([sys.executable, "-m", "enviro_data.osm_http", "--worker"],
                                input=json.dumps(message).encode(), capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise URLError(f"overall_request_deadline_exceeded_{timeout}s") from error
    if result.returncode != 0:
        raise URLError(f"http_worker_failed_exit_{result.returncode}")
    payload = json.loads(result.stdout)
    if payload.get("http_error"):
        raise HTTPError(request.full_url, payload["http_error"], payload["error"], payload.get("headers", {}), None)
    if payload.get("error"):
        raise URLError(payload["error"])
    return io.BytesIO(base64.b64decode(payload["data"]))


def worker():
    message = json.load(sys.stdin)
    data = base64.b64decode(message["data"]) if message["data"] is not None else None
    request = Request(message["url"], data=data, headers=message["headers"])
    try:
        with native_urlopen(request, timeout=message["timeout"]) as response:
            raw = response.read(8_000_001)
        result = {"data": base64.b64encode(raw).decode()}
    except HTTPError as error:
        headers = {"Retry-After": error.headers["Retry-After"]} if error.headers and error.headers.get("Retry-After") else {}
        result = {"http_error": error.code, "error": str(error), "headers": headers}
    except Exception as error:
        result = {"error": f"{type(error).__name__}: {error}"}
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__" and sys.argv[1:] == ["--worker"]:
    worker()
