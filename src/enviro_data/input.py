"""Load, normalize, and validate the immutable site overview CSV.

The module deliberately uses only the Python standard library. No operation in
this module mutates the source CSV or performs network access.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

EXPECTED_COLUMNS: tuple[str, ...] = (
    "sample_id",
    "Population.name",
    "population.abbreviation",
    "Latitude",
    "Longitude",
    "Ecotype",
)
CRS = "EPSG:4326"


@dataclass(frozen=True, slots=True)
class SiteRecord:
    """A normalized site row, with coordinates in WGS84 decimal degrees."""

    sample_id: str
    population_name: str
    population_abbreviation: str
    latitude: float
    longitude: float
    ecotype: str
    source_row: int
    crs: str = CRS


@dataclass(slots=True)
class InputDiagnostics:
    """Non-fatal and fatal findings produced while reading a site file."""

    rows_read: int = 0
    rows_valid: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def format(self) -> str:
        parts = [f"read {self.rows_read} row(s), {self.rows_valid} valid"]
        if self.errors:
            parts.append("errors: " + "; ".join(self.errors))
        if self.warnings:
            parts.append("warnings: " + "; ".join(self.warnings))
        return " | ".join(parts)


@dataclass(frozen=True, slots=True)
class SiteLoadResult:
    """Records plus diagnostics, allowing callers to choose strictness."""

    records: tuple[SiteRecord, ...]
    diagnostics: InputDiagnostics


class SiteInputError(ValueError):
    """Raised by :func:`load_sites` in strict mode for invalid input."""


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _parse_coordinate(raw: str, label: str, row_number: int, diagnostics: InputDiagnostics) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        diagnostics.errors.append(f"row {row_number}: {label} is not numeric ({raw!r})")
        return None
    if not math.isfinite(value):
        diagnostics.errors.append(f"row {row_number}: {label} must be finite")
        return None
    low, high = (-90.0, 90.0) if label == "Latitude" else (-180.0, 180.0)
    if not low <= value <= high:
        diagnostics.errors.append(f"row {row_number}: {label} outside [{low}, {high}]")
        return None
    return value


def load_sites(path: str | Path, *, strict: bool = False) -> SiteLoadResult:
    """Read and normalize a site CSV without modifying it.

    Invalid rows are omitted while their diagnostics are retained. Set
    ``strict=True`` to raise :class:`SiteInputError` after validation instead.
    Extra columns are accepted with a warning for forward compatibility; all
    six expected columns are required.
    """

    diagnostics = InputDiagnostics()
    records: list[SiteRecord] = []
    seen_ids: set[str] = set()
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        missing = [column for column in EXPECTED_COLUMNS if column not in columns]
        if missing:
            diagnostics.errors.append("missing required column(s): " + ", ".join(missing))
        extras = [column for column in columns if column not in EXPECTED_COLUMNS]
        if extras:
            diagnostics.warnings.append("ignored extra column(s): " + ", ".join(extras))
        if missing:
            result = SiteLoadResult(tuple(), diagnostics)
            if strict:
                raise SiteInputError(diagnostics.format())
            return result

        for row_number, row in enumerate(reader, start=2):
            diagnostics.rows_read += 1
            values = {column: _text(row.get(column)) for column in EXPECTED_COLUMNS}
            row_errors_before = len(diagnostics.errors)
            required = ("sample_id", "Population.name", "population.abbreviation", "Ecotype")
            for column in required:
                if not values[column]:
                    diagnostics.errors.append(f"row {row_number}: {column} is required")
            sample_id = values["sample_id"]
            if sample_id and sample_id in seen_ids:
                diagnostics.errors.append(f"row {row_number}: duplicate sample_id {sample_id!r}")
            latitude = _parse_coordinate(values["Latitude"], "Latitude", row_number, diagnostics)
            longitude = _parse_coordinate(values["Longitude"], "Longitude", row_number, diagnostics)
            if len(diagnostics.errors) != row_errors_before or latitude is None or longitude is None:
                continue
            seen_ids.add(sample_id)
            records.append(SiteRecord(
                sample_id=sample_id,
                population_name=values["Population.name"],
                population_abbreviation=values["population.abbreviation"].upper(),
                latitude=latitude,
                longitude=longitude,
                ecotype=values["Ecotype"].lower(),
                source_row=row_number,
            ))
            diagnostics.rows_valid += 1

    result = SiteLoadResult(tuple(records), diagnostics)
    if strict and diagnostics.has_errors:
        raise SiteInputError(diagnostics.format())
    return result
