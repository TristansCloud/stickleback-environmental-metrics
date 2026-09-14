"""Shared environmental metric and provenance contracts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class MetricProvenance:
    source_id: str
    source_version: str | None = None
    method: str | None = None
    spatial_scale_m: float | None = None
    retrieved_at_utc: str | None = None
    checksum_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class EnvironmentalMetric:
    name: str
    value: Any
    status: str
    ecological_axis: str
    unit: str | None = None
    provenance: MetricProvenance | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def as_flat_fields(self) -> dict[str, Any]:
        """Return stable wide-table columns while preserving missingness."""
        result = {
            self.name: self.value,
            f"{self.name}__status": self.status,
            f"{self.name}__unit": self.unit,
            f"{self.name}__axis": self.ecological_axis,
        }
        if self.provenance:
            result[f"{self.name}__source"] = self.provenance.source_id
            result[f"{self.name}__source_version"] = self.provenance.source_version
            result[f"{self.name}__method"] = self.provenance.method
            result[f"{self.name}__scale_m"] = self.provenance.spatial_scale_m
            result[f"{self.name}__retrieved_at_utc"] = self.provenance.retrieved_at_utc
            result[f"{self.name}__checksum_sha256"] = self.provenance.checksum_sha256
        result[f"{self.name}__diagnostics"] = json.dumps(
            dict(self.diagnostics), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ) if self.diagnostics else None
        return result
