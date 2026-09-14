"""Auditable numeric transforms declared by source-catalog variables."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransformResult:
    value: float | None
    status: str


def apply_source_transform(value: object, transform: str) -> TransformResult:
    if value is None or str(value).strip().lower() in {"", "none", "null", "nan"}:
        return TransformResult(None, "no_valid_data")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return TransformResult(None, "invalid_value")
    if not math.isfinite(number):
        return TransformResult(None, "invalid_value")
    functions = {
        "identity": lambda x: x,
        "kelvin_to_celsius": lambda x: x - 273.15,
        "m_to_mm": lambda x: x * 1000.0,
        "m_to_mm_nonnegative": lambda x: x * 1000.0 if x >= 0 else None,
        "scale_0.01": lambda x: x * 0.01,
        "scale_0.001": lambda x: x * 0.001,
        "scale_0.001_offset_20": lambda x: x * 0.001 + 20.0,
    }
    if transform not in functions:
        raise ValueError(f"unknown source transform: {transform}")
    transformed = functions[transform](number)
    return TransformResult(transformed, "ok" if transformed is not None else "invalid_value")
