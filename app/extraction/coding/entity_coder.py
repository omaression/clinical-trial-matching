import re
from dataclasses import dataclass, field

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.extraction.types import CodedConcept, Entity
from app.models.database import CodingLookup


@dataclass
class CodingResult:
    concepts: list[CodedConcept] = field(default_factory=list)
    confidence: float = 0.40
    review_required: bool = True
    review_reason: str | None = "uncoded_entity"


_SYSTEM_PRIORITY = ("mesh", "nci_thesaurus", "loinc")
_SYSTEMS_BY_LABEL = {
    "DISEASE": ("mesh",),
    "BIOMARKER": ("nci_thesaurus",),
    "DRUG": ("nci_thesaurus",),
    "PERF_SCALE": ("nci_thesaurus",),
    "LAB_TEST": ("loinc",),
}


class EntityCoder:
    """Stage 4: Map entities to MeSH / NCI Thesaurus / LOINC."""

    def __init__(self, db: Session):
        self._db = db

    def code_entity(self, entity: Entity) -> CodingResult:
        lookup_text = _normalize_text(entity.lookup_text)
        if not lookup_text:
            return CodingResult(
                concepts=[],
                confidence=0.40,
                review_required=True,
                review_reason="uncoded_entity",
            )
        systems = _SYSTEMS_BY_LABEL.get(entity.label, _SYSTEM_PRIORITY)

        # Tier 1: Exact match on display
        result = self._exact_match(lookup_text, systems)
        if result:
            return result

        # Tier 2: Synonym match
        result = self._synonym_match(entity.lookup_text, systems)
        if result:
            return result

        # Tier 3: Fuzzy match
        lookups = self._candidate_lookups(systems)
        result = self._fuzzy_match(lookup_text, lookups)
        if result:
            return result

        # Tier 4: No match
        return CodingResult(
            concepts=[],
            confidence=0.40,
            review_required=True,
            review_reason="uncoded_entity",
        )

    def _candidate_lookups(self, systems: tuple[str, ...]) -> list[CodingLookup]:
        lookups = (
            self._db.query(CodingLookup)
            .filter(CodingLookup.system.in_(systems))
            .all()
        )
        return sorted(
            lookups,
            key=lambda lookup: (
                _system_rank(lookup.system, systems),
                lookup.display.casefold(),
                lookup.code.casefold(),
            ),
        )

    def _exact_match(self, text: str, systems: tuple[str, ...]) -> CodingResult | None:
        matches = self._ordered_matches(
            self._db.query(CodingLookup)
            .filter(
                CodingLookup.system.in_(systems),
                _normalized_sql_text(CodingLookup.display) == text,
            )
            .all(),
            systems,
        )
        if matches:
            lookup = matches[0]
            return CodingResult(
                concepts=[CodedConcept(
                    system=lookup.system, code=lookup.code,
                    display=lookup.display, match_type="exact",
                )],
                confidence=0.95,
                review_required=False,
                review_reason=None,
            )
        return None

    def _synonym_match(self, raw_text: str, systems: tuple[str, ...]) -> CodingResult | None:
        synonym_variants = sorted(_sql_synonym_variants(raw_text))
        if not synonym_variants:
            return None
        matches = self._ordered_matches(
            self._db.query(CodingLookup)
            .filter(
                CodingLookup.system.in_(systems),
                or_(*(CodingLookup.synonyms.any(variant) for variant in synonym_variants)),
            )
            .all(),
            systems,
        )
        if matches:
            lookup = matches[0]
            return CodingResult(
                concepts=[CodedConcept(
                    system=lookup.system, code=lookup.code,
                    display=lookup.display, match_type="synonym",
                )],
                confidence=0.85,
                review_required=False,
                review_reason=None,
            )
        return None

    def _ordered_matches(
        self, lookups: list[CodingLookup], systems: tuple[str, ...]
    ) -> list[CodingLookup]:
        return sorted(
            lookups,
            key=lambda lookup: (
                _system_rank(lookup.system, systems),
                lookup.display.casefold(),
                lookup.code.casefold(),
            ),
        )

    def _fuzzy_match(self, text: str, lookups: list[CodingLookup]) -> CodingResult | None:
        best_match: CodingLookup | None = None
        best_distance = 3

        for lookup in lookups:
            d = _levenshtein(text, _normalize_text(lookup.display))
            if d <= 2 and d < best_distance:
                best_match = lookup
                best_distance = d

            for syn in (lookup.synonyms or []):
                d = _levenshtein(text, _normalize_text(syn))
                if d <= 2 and d < best_distance:
                    best_match = lookup
                    best_distance = d

        if best_match:
            return CodingResult(
                concepts=[CodedConcept(
                    system=best_match.system, code=best_match.code,
                    display=best_match.display, match_type="fuzzy",
                )],
                confidence=0.60,
                review_required=True,
                review_reason="fuzzy_match",
            )
        return None


def _normalize_text(text: str) -> str:
    normalized = text.casefold()
    normalized = re.sub(r"(?<=\w)\+(?=\s|$)", " positive ", normalized)
    normalized = re.sub(r"(?<=\w)-(?=\s|$)", " negative ", normalized)
    normalized = normalized.replace("+", " positive ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalized_sql_text(column):
    expression = func.lower(column)
    expression = func.replace(expression, "+", " positive ")
    expression = func.replace(expression, "/", " ")
    expression = func.replace(expression, "_", " ")
    expression = func.regexp_replace(expression, r"[^a-z0-9]+", " ", "g")
    expression = func.regexp_replace(expression, r"\s+", " ", "g")
    return func.trim(expression)


def _sql_synonym_variants(text: str) -> set[str]:
    stripped = text.strip()
    if not stripped:
        return set()
    variants = {
        stripped,
        stripped.casefold(),
        _normalize_text(text),
    }
    collapsed = re.sub(r"\s+", " ", stripped.replace("/", " ").replace("_", " ").strip())
    if collapsed:
        variants.add(collapsed)
        variants.add(collapsed.casefold())
    return {variant for variant in variants if variant}


def _system_rank(system: str, allowed_systems: tuple[str, ...]) -> int:
    if system in allowed_systems:
        return allowed_systems.index(system)
    if system in _SYSTEM_PRIORITY:
        return len(allowed_systems) + _SYSTEM_PRIORITY.index(system)
    return len(allowed_systems) + len(_SYSTEM_PRIORITY)


def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]
