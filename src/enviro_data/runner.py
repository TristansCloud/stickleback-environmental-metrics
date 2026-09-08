"""Offline-by-default pilot pipeline entrypoint.

The runner wires records to optional variable modules, but performs no network
requests unless a caller explicitly supplies a retriever/client. It is a
skeleton: enrichment adapters can be added without changing pilot selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .input import SiteRecord, load_sites
from .pilot import PilotConfig, select_pilot


@dataclass(frozen=True, slots=True)
class PilotRunResult:
    records: tuple[SiteRecord, ...]
    variables: tuple[dict[str, Any], ...]
    network_enabled: bool = False


def run_pilot(source: str | Path, *, config: PilotConfig | None = None,
              variable_modules: Iterable[Any] = (), network_enabled: bool = False) -> PilotRunResult:
    """Load, select, and invoke explicitly supplied variable modules.

    Modules may expose ``process(record, network_enabled=...)`` or be callable.
    With the default empty module list this function only validates and selects
    records; no OSM, climate, or terrain operation is attempted.
    """
    loaded = load_sites(source, strict=True)
    records = select_pilot(loaded.records, config)
    outputs: list[dict[str, Any]] = []
    for record in records:
        row: dict[str, Any] = {"sample_id": record.sample_id}
        for module in variable_modules:
            if hasattr(module, "process"):
                value = module.process(record, network_enabled=network_enabled)
            elif callable(module):
                value = module(record)
            else:
                raise TypeError(f"variable module is not callable: {module!r}")
            row[getattr(module, "name", module.__class__.__name__)] = value
        outputs.append(row)
    return PilotRunResult(records, tuple(outputs), network_enabled)
