"""Download checksum-verified country PBFs from a prepared coverage manifest.

The coverage manifest is a local JSON with regions[].id, name and urls.pbf.
Downloads are sequential, resumable, and never replace a verified file.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
from pathlib import Path
import shutil
import time
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)
HEADERS = {"User-Agent": "stickleback-environmental-metrics/0.1 (study extracts)"}


def request(url, *, method=None, headers=None):
    if not url.startswith(("https://download.geofabrik.de/", "https://ftp5.gwdg.de/pub/misc/openstreetmap/download.geofabrik.de/")):
        raise ValueError("expected official Geofabrik download URL")
    return urlopen(Request(url, headers={**HEADERS, **(headers or {})}, method=method), timeout=60)


def metadata(region):
    url = region["urls"]["pbf"]
    with request(url, method="HEAD") as response:
        # Latest redirects to a dated snapshot; pin bytes and checksum together.
        url = response.geturl()
        size = int(response.headers["Content-Length"])
        modified = response.headers.get("Last-Modified", "")
    with request(url + ".md5") as response:
        checksum = response.read().decode().split()[0]
    if len(checksum) != 32 or any(c not in "0123456789abcdef" for c in checksum.lower()):
        raise ValueError("invalid published MD5")
    return {"id": region["id"], "name": region["name"], "url": url,
            "bytes": size, "last_modified": modified, "md5": checksum.lower()}


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "md5").hexdigest()


def download(item, output):
    dest = output / (item["id"].replace("/", "_") + ".osm.pbf")
    part = dest.with_suffix(dest.suffix + ".part")
    if dest.exists():
        if dest.stat().st_size == item["bytes"] and digest(dest) == item["md5"]:
            LOG.info("verified_existing %s", item["name"])
            return str(dest)
        raise ValueError(f"existing file differs from manifest; retained: {dest}")
    for attempt in range(1, 4):
        try:
            offset = part.stat().st_size if part.exists() else 0
            if offset > item["bytes"]:
                raise ValueError(f"partial file exceeds expected size: {part}")
            if offset < item["bytes"]:
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                with request(item["url"], headers=headers) as response:
                    if offset and response.status == 206:
                        if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                            raise ValueError("unexpected Content-Range")
                        mode = "ab"
                    else:
                        offset, mode = 0, "wb"
                    LOG.info("download_start %s size_gb=%.3f offset=%d attempt=%d", item["name"], item["bytes"]/1e9, offset, attempt)
                    last_log = time.monotonic()
                    with part.open(mode) as file:
                        while chunk := response.read(4 * 1024 * 1024):
                            file.write(chunk)
                            offset += len(chunk)
                            if time.monotonic() - last_log > 30:
                                LOG.info("progress %s %.1f%%", item["name"], 100*offset/item["bytes"])
                                last_log = time.monotonic()
            if part.stat().st_size != item["bytes"] or digest(part) != item["md5"]:
                raise ValueError(f"checksum/size mismatch; retained partial file: {part}")
            part.replace(dest)
            LOG.info("verified_download %s bytes=%d", item["name"], item["bytes"])
            return str(dest)
        except (OSError, TimeoutError) as error:
            LOG.warning("request_failed %s attempt=%d error=%s", item["name"], attempt, error)
            if attempt == 3:
                raise
            time.sleep(2 * attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, default=Path("data/cache/geofabrik/study_coverage.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/cache/geofabrik/study_pbf"))
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "download_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        coverage = json.loads(args.coverage.read_text(encoding="utf-8"))
        if coverage.get("uncovered"):
            raise ValueError("coverage has unmatched sites")
        with ThreadPoolExecutor(max_workers=4) as pool:
            items = list(pool.map(metadata, coverage["regions"]))
        manifest = {"source": "OpenStreetMap contributors / Geofabrik, ODbL", "items": items, "completed": {}}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total = sum(item["bytes"] for item in manifest["items"])
    LOG.info("plan regions=%d total_gb=%.3f free_gb=%.3f", len(manifest["items"]), total/1e9, shutil.disk_usage(args.output_dir).free/1e9)
    if not args.download:
        return
    existing = sum(p.stat().st_size for p in args.output_dir.glob("*.osm.pbf*"))
    if shutil.disk_usage(args.output_dir).free < max(0, total-existing) + 3*1024**3:
        raise ValueError("insufficient free disk space")
    for item in manifest["items"]:
        manifest["completed"][item["id"]] = download(item, args.output_dir)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    LOG.info("all_downloads_verified regions=%d", len(manifest["items"]))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
