import re
from dataclasses import dataclass, field

from sqlalchemy import bindparam, func, or_, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import settings
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
_FUZZY_STOPWORDS = {
    "and",
    "or",
    "of",
    "the",
    "to",
    "in",
    "for",
    "with",
    "without",
    "history",
    "current",
    "active",
    "prior",
    "therapy",
    "treatment",
    "disease",
    "disorder",
    "syndrome",
    "cancer",
    "carcinoma",
    "neoplasm",
    "neoplasms",
    "tumor",
    "tumors",
    "malignancy",
    "malignant",
    "study",
    "intervention",
    "protocol",
    "participants",
    "patient",
}


class EntityCoder:
    """Stage 4: Map entities to MeSH / NCI Thesaurus / LOINC."""

    def __init__(self, db: Session):
        self._db = db

    def code_entity(self, entity: Entity) -> CodingResult:
        systems = _SYSTEMS_BY_LABEL.get(entity.label)
        if not systems:
            return CodingResult(
                concepts=[],
                confidence=0.0,
                review_required=False,
                review_reason=None,
            )
        lookup_variants = _lookup_variants(entity)
        if not lookup_variants:
            return CodingResult(
                concepts=[],
                confidence=0.40,
                review_required=True,
                review_reason="uncoded_entity",
            )

        # Tier 1: Exact match on display
        for lookup_text in lookup_variants:
            result = self._exact_match(_normalize_text(lookup_text), systems)
            if result:
                return result

        # Tier 2: Synonym match
        for lookup_text in lookup_variants:
            result = self._synonym_match(lookup_text, systems)
            if result:
                return result

        # Tier 3: Fuzzy match via pg_trgm similarity, with a safe Python fallback.
        result = self._fuzzy_match(lookup_variants, systems)
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

    def _fuzzy_match(self, variants: list[str], systems: tuple[str, ...]) -> CodingResult | None:
        for text in variants:
            normalized = _normalize_text(text)
            try:
                result = self._pg_trgm_fuzzy_match(normalized, systems)
                if result:
                    return result
            except DBAPIError:
                self._db.rollback()

        lookups = self._candidate_lookups(systems)
        for text in variants:
            result = self._fallback_fuzzy_match(_normalize_text(text), lookups)
            if result:
                return result
        return None

    def _pg_trgm_fuzzy_match(self, text: str, systems: tuple[str, ...]) -> CodingResult | None:
        statement = text_query().bindparams(bindparam("systems", expanding=True))
        rows = self._db.execute(
            statement,
            {
                "lookup_text": text,
                "systems": list(systems),
                "threshold": settings.coding_fuzzy_similarity_threshold,
            },
        ).mappings().all()
        if not rows:
            return None

        ranked_matches = sorted(
            rows,
            key=lambda row: (
                -float(row["score"]),
                _system_rank(str(row["system"]), systems),
                str(row["display"]).casefold(),
                str(row["code"]).casefold(),
            ),
        )
        best_match = next(
            (
                row for row in ranked_matches
                if _is_viable_fuzzy_candidate(
                    text=text,
                    display=str(row["display"]),
                    synonyms=row.get("synonyms"),
                )
            ),
            None,
        )
        if not best_match:
            return None
        return CodingResult(
            concepts=[CodedConcept(
                system=best_match["system"],
                code=best_match["code"],
                display=best_match["display"],
                match_type="fuzzy",
            )],
            confidence=0.60,
            review_required=True,
            review_reason="fuzzy_match",
        )

    def _fallback_fuzzy_match(self, text: str, lookups: list[CodingLookup]) -> CodingResult | None:
        best_match: CodingLookup | None = None
        best_distance = 3

        for lookup in lookups:
            if not _is_viable_fuzzy_candidate(text=text, display=lookup.display, synonyms=lookup.synonyms):
                continue
            d = _levenshtein(text, _normalize_text(lookup.display))
            if d <= 2 and d < best_distance:
                best_match = lookup
                best_distance = d

            for syn in (lookup.synonyms or []):
                if not _is_viable_fuzzy_candidate(text=text, display=syn, synonyms=None):
                    continue
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


def text_query():
    return text(
        """
        SELECT
            id,
            system,
            code,
            display,
            synonyms,
            GREATEST(
                similarity(
                    trim(
                        regexp_replace(
                            regexp_replace(
                                replace(
                                    replace(replace(lower(display), '+', ' positive '), '/', ' '),
                                    '_',
                                    ' '
                                ),
                                '[^a-z0-9]+',
                                ' ',
                                'g'
                            ),
                            '\\s+',
                            ' ',
                            'g'
                        )
                    ),
                    :lookup_text
                ),
                COALESCE(
                    (
                        SELECT MAX(
                            similarity(
                                trim(
                                    regexp_replace(
                                        regexp_replace(
                                            replace(
                                                replace(replace(lower(synonym), '+', ' positive '), '/', ' '),
                                                '_',
                                                ' '
                                            ),
                                            '[^a-z0-9]+',
                                            ' ',
                                            'g'
                                        ),
                                        '\\s+',
                                        ' ',
                                        'g'
                                    )
                                ),
                                :lookup_text
                            )
                        )
                        FROM unnest(COALESCE(coding_lookups.synonyms, ARRAY[]::text[])) AS synonym
                    ),
                    0
                )
            ) AS score
        FROM coding_lookups
        WHERE system IN :systems
          AND GREATEST(
                similarity(
                    trim(
                        regexp_replace(
                            regexp_replace(
                                replace(
                                    replace(replace(lower(display), '+', ' positive '), '/', ' '),
                                    '_',
                                    ' '
                                ),
                                '[^a-z0-9]+',
                                ' ',
                                'g'
                            ),
                            '\\s+',
                            ' ',
                            'g'
                        )
                    ),
                    :lookup_text
                ),
                COALESCE(
                    (
                        SELECT MAX(
                            similarity(
                                trim(
                                    regexp_replace(
                                        regexp_replace(
                                            replace(
                                                replace(replace(lower(synonym), '+', ' positive '), '/', ' '),
                                                '_',
                                                ' '
                                            ),
                                            '[^a-z0-9]+',
                                            ' ',
                                            'g'
                                        ),
                                        '\\s+',
                                        ' ',
                                        'g'
                                    )
                                ),
                                :lookup_text
                            )
                        )
                        FROM unnest(COALESCE(coding_lookups.synonyms, ARRAY[]::text[])) AS synonym
                    ),
                    0
                )
            ) >= :threshold
        """
    )


def _normalize_text(text: str) -> str:
    normalized = text.casefold()
    normalized = re.sub(r"(?<=\w)\+(?=\s|$)", " positive ", normalized)
    normalized = re.sub(r"(?<=\w)-(?=\s|$)", " negative ", normalized)
    normalized = normalized.replace("+", " positive ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _lookup_variants(entity: Entity) -> list[str]:
    variants: list[str] = []
    for value in (entity.text, entity.expanded_text):
        if not value:
            continue
        normalized = value.strip()
        if normalized and normalized not in variants:
            variants.append(normalized)
    return variants


def _informative_tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        token
        for token in _normalize_text(text).split()
        if token and token not in _FUZZY_STOPWORDS
    }


def _is_viable_fuzzy_candidate(text: str, display: str, synonyms: list[str] | None) -> bool:
    source_tokens = _informative_tokens(text)
    if not source_tokens:
        return False

    candidate_token_sets = [_informative_tokens(display)]
    for synonym in synonyms or []:
        candidate_token_sets.append(_informative_tokens(synonym))

    viable_overlap = False
    for tokens in candidate_token_sets:
        if not tokens:
            continue
        overlap = source_tokens.intersection(tokens)
        if not overlap:
            continue
        overlap_ratio = len(overlap) / len(tokens)
        if len(tokens) <= 2 or overlap_ratio >= 0.5 or tokens.issubset(source_tokens):
            viable_overlap = True
            break
    return viable_overlap


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
