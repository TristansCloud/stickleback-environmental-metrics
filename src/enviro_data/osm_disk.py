"""Disk-space accounting for OSM download caches."""
import logging
import shutil

MIN_FREE_BYTES = 60_000_000_000
LOG = logging.getLogger(__name__)


def require_space(path, incoming_bytes):
    """Check the volume that holds the cache, including the space to write."""
    free = shutil.disk_usage(path).free
    if free < MIN_FREE_BYTES + incoming_bytes:
        raise ValueError(
            f"OSM cache has {free / 1e9:.3f} GB free; "
            f"need {(MIN_FREE_BYTES + incoming_bytes) / 1e9:.3f} GB "
            f"to write {incoming_bytes:,} bytes and keep 60 GB free"
        )


def log_usage(directory):
    cached = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
    LOG.info("osm_cache path=%s cached_bytes=%d free_bytes=%d reserve_bytes=%d",
             directory, cached, shutil.disk_usage(directory).free, MIN_FREE_BYTES)
