"""Bounded, cache-first acquisition of pilot DEM/hydrology tiles.

This module deliberately does not discover tiles or perform a download unless a
caller explicitly enables it.  A cached object is accepted only when its sidecar
metadata is complete and its checksum still matches the object on disk.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
try:  # Python 3.11+ standard library
    import tomllib
except ModuleNotFoundError:  # Python 3.10: optional backport
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # defer the actionable error until config loading
        tomllib = None  # type: ignore[assignment]
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping


class MetadataError(ValueError):
    """A cached raster has incomplete or inconsistent source metadata."""


@dataclass(frozen=True, slots=True)
class RasterMetadata:
    source_url: str
    item_id: str
    provider: str
    retrieval_date: str
    checksum_sha256: str
    source_crs: str
    vertical_datum: str
    resolution_m: float
    local_cached_path: str
    nodata: float | None = None
    zero_is_ocean_nodata: bool = False

    def validate(self, object_path: str | Path | None = None) -> None:
        required = ("source_url", "item_id", "provider", "retrieval_date",
                    "checksum_sha256", "source_crs", "vertical_datum",
                    "local_cached_path")
        missing = [name for name in required if not getattr(self, name)]
        if missing:
            raise MetadataError("missing raster metadata: " + ", ".join(missing))
        if self.source_crs.upper() not in {"EPSG:4326", "EPSG:3857"} and not self.source_crs.upper().startswith("EPSG:"):
            raise MetadataError(f"source_crs must be an EPSG code, got {self.source_crs!r}")
        if self.resolution_m <= 0:
            raise MetadataError("resolution_m must be positive")
        if len(self.checksum_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.checksum_sha256.lower()):
            raise MetadataError("checksum_sha256 must be a SHA-256 hex digest")
        if object_path is not None:
            path = Path(object_path)
            if not path.is_file():
                raise MetadataError(f"cached raster is missing: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest.lower() != self.checksum_sha256.lower():
                raise MetadataError(f"checksum mismatch for cached raster: {path}")


@dataclass(frozen=True, slots=True)
class AcquisitionConfig:
    """Configuration boundary for one pilot run; defaults are intentionally bounded."""
    cache_dir: Path
    pilot_sites_csv: Path
    max_sites: int = 40
    network_enabled: bool = False
    read_timeout_s: float = 30.0
    max_download_bytes: int = 500_000_000

    def validate(self) -> None:
        if self.max_sites != 40:
            raise ValueError("this phase is restricted to the deterministic 40-site pilot")
        if self.read_timeout_s <= 0 or self.max_download_bytes <= 0:
            raise ValueError("download bounds must be positive")

    @classmethod
    def from_toml(cls, path: str | Path) -> "AcquisitionConfig":
        if tomllib is None:
            raise RuntimeError("TOML configuration requires Python 3.11+ or the 'tomli' package on Python 3.10")
        config_path = Path(path)
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
        values = {key: payload[key] for key in ("cache_dir", "pilot_sites_csv", "max_sites",
                                                 "network_enabled", "read_timeout_s", "max_download_bytes")
                  if key in payload}
        values["cache_dir"] = Path(values["cache_dir"])
        values["pilot_sites_csv"] = Path(values["pilot_sites_csv"])
        if not values["cache_dir"].is_absolute():
            values["cache_dir"] = config_path.parent / values["cache_dir"]
        if not values["pilot_sites_csv"].is_absolute():
            values["pilot_sites_csv"] = config_path.parent / values["pilot_sites_csv"]
        result = cls(**values)
        result.validate()
        return result


Fetcher = Callable[[str, Path, int], None]


def _default_fetcher(url: str, target: Path, max_bytes: int) -> None:
    request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=30) as response, target.open("wb") as out:
        total = 0
        while chunk := response.read(min(1024 * 1024, max_bytes - total)):
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"download exceeds configured bound ({max_bytes} bytes)")
            out.write(chunk)


class CacheFirstAcquirer:
    """Resolve a local cache entry and optionally acquire exactly one requested object."""
    def __init__(self, config: AcquisitionConfig, fetcher: Fetcher | None = None):
        config.validate()
        self.config = config
        self.fetcher = fetcher or (lambda url, path, limit: _default_fetcher(url, path, limit))

    def resolve(self, metadata: RasterMetadata, *, allow_network: bool | None = None) -> Path:
        """Return a verified cache path; missing coverage requires explicit network access."""
        path = Path(metadata.local_cached_path)
        if not path.is_absolute():
            path = self.config.cache_dir / path
        if path.is_file():
            sidecar = path.with_suffix(path.suffix + ".json")
            if not sidecar.is_file():
                raise MetadataError(f"provenance sidecar is missing: {sidecar}")
            cached_metadata = self.metadata_from_json(sidecar)
            cached_metadata.validate(path)
            if cached_metadata.checksum_sha256.lower() != metadata.checksum_sha256.lower():
                raise MetadataError("requested metadata does not match cached provenance")
            metadata.validate(path)
            return path
        enabled = self.config.network_enabled if allow_network is None else allow_network
        if not enabled:
            raise FileNotFoundError(f"DEM coverage is not cached: {path}; network acquisition is disabled")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        self.fetcher(metadata.source_url, tmp, self.config.max_download_bytes)
        tmp.replace(path)
        metadata.validate(path)
        self.write_sidecar(metadata, path)
        return path

    @staticmethod
    def write_sidecar(metadata: RasterMetadata, path: str | Path) -> Path:
        path = Path(path)
        metadata.validate(path)
        sidecar = path.with_suffix(path.suffix + ".json")
        sidecar.write_text(json.dumps(asdict(metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return sidecar

    @staticmethod
    def metadata_from_json(path: str | Path) -> RasterMetadata:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return RasterMetadata(**payload)


def retrieval_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
