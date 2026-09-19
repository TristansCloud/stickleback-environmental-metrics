"""Auditable waterbody-type inference from site names and broad ecotypes.

Name parsing is intentionally conservative.  It supplies a working hypothesis
for retrieval and review; it is not treated as independently verified habitat.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from .habitats import HabitatDomain, normalize_habitat


@dataclass(frozen=True, slots=True)
class HabitatInference:
    name_inferred_waterbody_type: str
    matched_terms: tuple[str, ...]
    name_inference_confidence: str
    working_waterbody_type: str
    working_type_basis: str
    manual_review: bool


_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "transition",
        (
            r"\bestuar(?:y|ine)\b",
            r"\blagoon\b",
            r"\bmarsh\b",
            r"\briver\s+mouth\b",
            r"\bcreek\s+mouth\b",
            r"\bstream\s+mouth\b",
        ),
    ),
    (
        "lake",
        (
            r"\blake\b",
            r"\bpond\b",
            r"\breservoir\b",
            r"\bloch\b",
            r"\blough\b",
            r"\b\w*vatn\w*\b",
            r"\b\w*(?:jarvi|jaervi)\w*\b",
            r"\b\w*molledam\w*\b",
        ),
    ),
    (
        "stream",
        (
            r"\briver\b",
            r"\bstream\b",
            r"\bcreek\b",
            r"\bbrook\b",
            r"\btributar(?:y|ies)\b",
        ),
    ),
    (
        "marine",
        (
            r"\bsea\b",
            r"\bocean\b",
            r"\bpelagic\b",
            r"\bmarine\b",
            r"\bbay\b",
            r"\bharbou?r\b",
            r"\bfj(?:ord|orth)\b",
            r"\bsound\b",
            r"\bstrait\b",
            r"\bbeach\b",
        ),
    ),
)


def normalize_site_name(value: object) -> str:
    """Return lower-case ASCII-ish tokens while preserving word boundaries."""
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def _matches(name: str, patterns: Iterable[str]) -> tuple[str, ...]:
    found: list[str] = []
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            found.append(match.group(0).strip())
    return tuple(dict.fromkeys(found))


def infer_site_habitat(population_name: object, ecotype: object) -> HabitatInference:
    """Infer a waterbody type, retaining evidence and any domain conflict."""
    name = normalize_site_name(population_name)
    hits = [(kind, _matches(name, patterns)) for kind, patterns in _PATTERNS]
    hits = [(kind, terms) for kind, terms in hits if terms]

    if not hits:
        name_type, terms, confidence = "unknown", (), "none"
    elif len(hits) == 1:
        name_type, terms, confidence = hits[0][0], hits[0][1], "high"
    else:
        # Transition phrases such as "River mouth" deliberately outrank their
        # component river cue, but all evidence remains visible.
        types = {kind for kind, _ in hits}
        if "transition" in types:
            name_type = "transition"
            confidence = "high"
        else:
            name_type = hits[0][0]
            confidence = "low"
        terms = tuple(term for _, group in hits for term in group)

    domain = normalize_habitat(ecotype)
    manual_review = confidence == "low"

    if domain is HabitatDomain.TRANSITION:
        working, basis = "transition", "ecotype:marine-freshwater"
        manual_review = manual_review or name_type not in {"unknown", "transition"}
    elif domain is HabitatDomain.MARINE:
        working, basis = "marine", "ecotype:marine"
        manual_review = manual_review or name_type in {"lake", "stream", "transition"}
    elif domain is HabitatDomain.FRESHWATER:
        if name_type in {"lake", "stream"}:
            working, basis = name_type, "population_name"
        elif name_type in {"marine", "transition"}:
            working, basis = name_type, "population_name_conflicts_with_freshwater_ecotype"
            manual_review = True
        else:
            working, basis = "unknown", "insufficient_name_evidence"
            manual_review = True
    else:
        working, basis = name_type, "population_name"

    return HabitatInference(
        name_inferred_waterbody_type=name_type,
        matched_terms=terms,
        name_inference_confidence=confidence,
        working_waterbody_type=working,
        working_type_basis=basis,
        manual_review=manual_review,
    )
