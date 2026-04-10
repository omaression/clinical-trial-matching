from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.extraction.types import CodedConcept, Entity
from app.models.database import CodingLookup


@dataclass
class CodingResult:
    concepts: list[CodedConcept] = field(default_factory=list)
    confidence: float = 0.40
    review_required: bool = True
    review_reason: str | None = "uncoded_entity"


class EntityCoder:
    """Stage 4: Map entities to MeSH / NCI Thesaurus / LOINC."""

    def __init__(self, db: Session):
        self._db = db

    def code_entity(self, entity: Entity) -> CodingResult:
        lookup_text = entity.lookup_text

        # Tier 1: Exact match on display
        result = self._exact_match(lookup_text)
        if result:
            return result

        # Tier 2: Synonym match
        result = self._synonym_match(lookup_text)
        if result:
            return result

        # Tier 3: Fuzzy match
        result = self._fuzzy_match(lookup_text)
        if result:
            return result

        # Tier 4: No match
        return CodingResult(
            concepts=[],
            confidence=0.40,
            review_required=True,
            review_reason="uncoded_entity",
        )

    def _exact_match(self, text: str) -> CodingResult | None:
        lookup = self._db.query(CodingLookup).filter(
            func.lower(CodingLookup.display) == text.lower()
        ).first()
        if lookup:
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

    def _synonym_match(self, text: str) -> CodingResult | None:
        lookup = self._db.query(CodingLookup).filter(
            CodingLookup.synonyms.any(func.lower(text))
        ).first()
        if lookup:
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

    def _fuzzy_match(self, text: str) -> CodingResult | None:
        lookups = self._db.query(CodingLookup).all()
        best_match = None
        best_distance = 3

        for lookup in lookups:
            d = _levenshtein(text.lower(), lookup.display.lower())
            if d <= 2 and d < best_distance:
                best_match = lookup
                best_distance = d

            for syn in (lookup.synonyms or []):
                d = _levenshtein(text.lower(), syn.lower())
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
