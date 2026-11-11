"""Cache small OpenStreetMap API map extracts for local candidate lookup."""
import argparse
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
import tempfile
from urllib.parse import urlencode
from urllib.request import Request

from .osm_disk import log_usage, require_space
from .osm_http import bounded_urlopen

ENDPOINT = "https://api.openstreetmap.org/api/0.6/map.json"
MAX_BYTES = 8_000_000
LOG = logging.getLogger(__name__)


def cached_map(bbox, directory, *, download=False):
    """Return the raw JSON path for a west, south, east, north WGS84 box."""
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Expected a valid west south east north bounding box")
    if east - west > Decimal("0.1") or north - south > Decimal("0.1"):
        raise ValueError("Use a small site box (at most 0.1° per side) or a regional extract")
    query = urlencode({"bbox": ",".join(format(v.normalize() if v else Decimal(0), "f") for v in bbox)})
    url = f"{ENDPOINT}?{query}"
    key = hashlib.sha256(url.encode("ascii")).hexdigest()
    target = directory / f"{key}.json"
    if target.is_file():
        LOG.info("cache_hit %s", url)
        log_usage(directory)
        return target
    if not download:
        raise FileNotFoundError(f"No cached response for {url}; use --download")

    directory.mkdir(parents=True, exist_ok=True)
    require_space(directory, MAX_BYTES)
    LOG.info("cache_miss %s", url)
    request = Request(url, headers={"User-Agent": "stickleback-environmental-metrics/0.1 (site review)"})
    with bounded_urlopen(request) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("OSM map response exceeded 8 MB; use a smaller bounding box")
    if not isinstance(json.loads(raw).get("elements"), list):
        raise ValueError("Expected an OSM JSON response with an elements list")
    require_space(directory, len(raw))
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as file:
        partial = Path(file.name)
        try:
            with file:
                file.write(raw)
            try:
                partial.rename(target)
            except FileExistsError:
                LOG.info("cache_filled_concurrently %s", url)
        finally:
            partial.unlink(missing_ok=True)
    log_usage(directory)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", required=True, nargs=4, type=Decimal,
                        metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/osm_map"))
    parser.add_argument("--download", action="store_true", help="Fetch a cache miss")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(cached_map(args.bbox, args.cache_dir, download=args.download))


if __name__ == "__main__":
    main()
