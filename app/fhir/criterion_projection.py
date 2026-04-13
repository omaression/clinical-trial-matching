from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.fhir.models import Annotation, CodeableConcept, Coding, MedicationStatement, Reference
from app.models.database import CodingLookup
from app.scripts.seed import MEDRT_DRUG_CLASSES, RXNORM_DRUGS, SNOMED_MEDICATION_CLASSES

RXNORM_SYSTEM_URI = "http://www.nlm.nih.gov/research/umls/rxnorm"
SNOMED_SYSTEM_URI = "http://snomed.info/sct"
MEDRT_SYSTEM_URI = "http://va.gov/terminology/medrt"

_SYSTEM_URIS = {
    "rxnorm": RXNORM_SYSTEM_URI,
    "snomed_ct": SNOMED_SYSTEM_URI,
    "medrt": MEDRT_SYSTEM_URI,
}
_MEDICATION_PROJECTION_CATEGORIES = {"prior_therapy", "concomitant_medication"}
_RAW_RECOGNIZED_CLASS_TERMS = {
    "pd-1 therapy",
    "pd-1/pd-l1 therapy",
    "pd-1/pd-l1 inhibitor therapy",
    "pd-l1 therapy",
    "kras-targeted therapy",
    "systemic corticosteroids",
    "live-attenuated vaccine",
    "live vaccine",
    "live or live-attenuated vaccine",
    "cyp3a4 inhibitors/inducers",
    "platinum-based chemotherapy",
}
_AMBIGUOUS_CLASS_HINTS = (
    "therapy",
    "vaccine",
    "corticosteroid",
    "steroid",
    "chemotherapy",
    "inhibitor",
    "inducer",
    "immunosuppressive",
    "targeted",
    "targeting",
    "antibody",
    "agent",
)


@dataclass(frozen=True)
class ProjectionLookup:
    system: str
    code: str
    display: str
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionResult:
    mention_text: str
    normalized_term: str
    criterion_id: UUID | None
    trial_id: UUID | None
    criterion_category: str
    criterion_type: str
    resource_type: str | None
    projection_status: str
    terminology_status: str
    review_required: bool
    system: str | None = None
    code: str | None = None
    display: str | None = None
    resource: dict[str, Any] | None = None


class CriterionProjectionMapper:
    def __init__(self, db: Session | None = None):
        self._db = db
        self._cached_lookup_index: dict[str, list[ProjectionLookup]] | None = None

    def project_criterion(self, criterion) -> list[ProjectionResult]:
        category = getattr(criterion, "category", None)
        if category not in _MEDICATION_PROJECTION_CATEGORIES:
            return []

        results: list[ProjectionResult] = []
        for mention_text in self._medication_mentions(criterion):
            normalized_term = _normalize_term(mention_text)
            projection = self._project_medication_mention(
                criterion,
                mention_text=mention_text,
                normalized_term=normalized_term,
            )
            if projection is not None:
                results.append(projection)
        return results

    def _project_medication_mention(
        self,
        criterion,
        *,
        mention_text: str,
        normalized_term: str,
    ) -> ProjectionResult | None:
        if not normalized_term:
            return None

        rxnorm_lookup = self._exact_or_synonym_lookup(normalized_term, systems=("rxnorm",))
        if rxnorm_lookup:
            resource = self._medication_statement_resource(
                criterion=criterion,
                mention_text=mention_text,
                lookup=rxnorm_lookup,
            )
            return ProjectionResult(
                mention_text=mention_text,
                normalized_term=normalized_term,
                criterion_id=getattr(criterion, "id", None),
                trial_id=getattr(criterion, "trial_id", None),
                criterion_category=getattr(criterion, "category", ""),
                criterion_type=getattr(criterion, "type", ""),
                resource_type="MedicationStatement",
                projection_status="projected",
                terminology_status="rxnorm_grounded",
                review_required=False,
                system=rxnorm_lookup.system,
                code=rxnorm_lookup.code,
                display=rxnorm_lookup.display,
                resource=resource,
            )

        class_lookup = self._exact_or_synonym_lookup(normalized_term, systems=("medrt", "snomed_ct"))
        if class_lookup:
            resource = self._medication_statement_resource(
                criterion=criterion,
                mention_text=mention_text,
                lookup=class_lookup,
            )
            return ProjectionResult(
                mention_text=mention_text,
                normalized_term=normalized_term,
                criterion_id=getattr(criterion, "id", None),
                trial_id=getattr(criterion, "trial_id", None),
                criterion_category=getattr(criterion, "category", ""),
                criterion_type=getattr(criterion, "type", ""),
                resource_type="MedicationStatement",
                projection_status="projected",
                terminology_status=f"{class_lookup.system}_grounded",
                review_required=False,
                system=class_lookup.system,
                code=class_lookup.code,
                display=class_lookup.display,
                resource=resource,
            )

        if self._is_recognized_class_term(normalized_term):
            return ProjectionResult(
                mention_text=mention_text,
                normalized_term=normalized_term,
                criterion_id=getattr(criterion, "id", None),
                trial_id=getattr(criterion, "trial_id", None),
                criterion_category=getattr(criterion, "category", ""),
                criterion_type=getattr(criterion, "type", ""),
                resource_type=None,
                projection_status="blocked_missing_class_code",
                terminology_status="recognized_class_missing_safe_code",
                review_required=True,
            )

        if self._looks_like_ambiguous_class(normalized_term):
            return ProjectionResult(
                mention_text=mention_text,
                normalized_term=normalized_term,
                criterion_id=getattr(criterion, "id", None),
                trial_id=getattr(criterion, "trial_id", None),
                criterion_category=getattr(criterion, "category", ""),
                criterion_type=getattr(criterion, "type", ""),
                resource_type=None,
                projection_status="review_required_ambiguous_class",
                terminology_status="ambiguous_class_no_safe_code",
                review_required=True,
            )

        return ProjectionResult(
            mention_text=mention_text,
            normalized_term=normalized_term,
            criterion_id=getattr(criterion, "id", None),
            trial_id=getattr(criterion, "trial_id", None),
            criterion_category=getattr(criterion, "category", ""),
            criterion_type=getattr(criterion, "type", ""),
            resource_type=None,
            projection_status="blocked_missing_rxnorm",
            terminology_status="named_drug_missing_rxnorm",
            review_required=True,
        )

    def _medication_mentions(self, criterion) -> list[str]:
        mentions: list[str] = []
        entities = getattr(criterion, "entities", None) or []
        for entity in entities:
            if getattr(entity, "label", None) != "DRUG":
                continue
            self._append_unique(mentions, getattr(entity, "expanded_text", None) or getattr(entity, "text", None))

        self._append_unique(mentions, getattr(criterion, "value_text", None))

        for exception_entity in getattr(criterion, "exception_entities", None) or []:
            self._append_unique(mentions, exception_entity)

        allowance_text = getattr(criterion, "allowance_text", None)
        if allowance_text:
            embedded_named_drug = self._named_drugs_in_text(allowance_text)
            for mention in embedded_named_drug:
                self._append_unique(mentions, mention)

        return mentions

    def _medication_statement_resource(
        self,
        criterion,
        *,
        mention_text: str,
        lookup: ProjectionLookup,
    ) -> dict[str, Any]:
        trial_id = getattr(criterion, "trial_id", None)
        criterion_id = getattr(criterion, "id", None)
        resource = MedicationStatement(
            status="unknown",
            subject=Reference(reference=f"Group/trial-{trial_id}" if trial_id else "Group/eligibility-cohort"),
            medicationCodeableConcept=CodeableConcept(
                coding=[
                    Coding(
                        system=_SYSTEM_URIS.get(lookup.system, lookup.system),
                        code=lookup.code,
                        display=lookup.display,
                    )
                ],
                text=mention_text,
            ),
            derivedFrom=[
                Reference(reference=f"ResearchStudy/{trial_id}") if trial_id else Reference(reference="ResearchStudy")
            ],
            note=[
                Annotation(text=getattr(criterion, "original_text", mention_text)),
            ],
        )
        payload = resource.model_dump(exclude_none=True)
        if criterion_id:
            payload["identifier"] = [{"system": "urn:ctm:criterion", "value": str(criterion_id)}]
        timeframe_operator = getattr(criterion, "timeframe_operator", None)
        timeframe_value = getattr(criterion, "timeframe_value", None)
        timeframe_unit = getattr(criterion, "timeframe_unit", None)
        if timeframe_operator and timeframe_value is not None and timeframe_unit:
            payload.setdefault("note", []).append(
                {"text": f"timeframe: {timeframe_operator} {timeframe_value:g} {timeframe_unit}"}
            )
        return payload

    def _exact_or_synonym_lookup(
        self,
        normalized_term: str,
        *,
        systems: tuple[str, ...],
    ) -> ProjectionLookup | None:
        for lookup in self._lookup_index().get(normalized_term, []):
            if lookup.system in systems:
                return lookup
        return None

    def _named_drugs_in_text(self, text: str) -> list[str]:
        normalized_text = _normalize_term(text)
        matches: list[tuple[int, str]] = []
        for normalized_phrase, lookups in self._lookup_index().items():
            if not any(lookup.system == "rxnorm" for lookup in lookups):
                continue
            if _contains_normalized_phrase(normalized_text, normalized_phrase):
                matches.append((len(normalized_phrase), lookups[0].display))
        matches.sort(reverse=True)
        unique: list[str] = []
        for _length, display in matches:
            self._append_unique(unique, display)
        return unique

    def _lookup_index(self) -> dict[str, list[ProjectionLookup]]:
        if self._cached_lookup_index is not None:
            return self._cached_lookup_index

        rows: list[ProjectionLookup] = []
        if self._db is not None:
            lookups = (
                self._db.query(CodingLookup)
                .filter(CodingLookup.system.in_(("rxnorm", "medrt", "snomed_ct")))
                .all()
            )
            for lookup in lookups:
                rows.append(
                    ProjectionLookup(
                        system=lookup.system,
                        code=lookup.code,
                        display=lookup.display,
                        synonyms=tuple(lookup.synonyms or []),
                    )
                )
        else:
            for system, catalog in (
                ("rxnorm", RXNORM_DRUGS),
                ("medrt", MEDRT_DRUG_CLASSES),
                ("snomed_ct", SNOMED_MEDICATION_CLASSES),
            ):
                for code, display, synonyms in catalog:
                    rows.append(
                        ProjectionLookup(
                            system=system,
                            code=code,
                            display=display,
                            synonyms=tuple(synonyms),
                        )
                    )

        index: dict[str, list[ProjectionLookup]] = {}
        for row in rows:
            for value in (row.display, *row.synonyms):
                normalized = _normalize_term(value)
                if not normalized:
                    continue
                index.setdefault(normalized, []).append(row)
        self._cached_lookup_index = index
        return index

    def _is_recognized_class_term(self, normalized_term: str) -> bool:
        return normalized_term in _RECOGNIZED_CLASS_TERMS

    def _looks_like_ambiguous_class(self, normalized_term: str) -> bool:
        return any(token in normalized_term for token in _AMBIGUOUS_CLASS_HINTS)

    @staticmethod
    def _append_unique(target: list[str], value: str | None) -> None:
        if not value:
            return
        normalized = value.strip()
        if not normalized:
            return
        key = _normalize_term(normalized)
        if key and all(_normalize_term(existing) != key for existing in target):
            target.append(normalized)


def _normalize_term(value: str | None) -> str:
    if not value:
        return ""
    collapsed = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return re.sub(r"\s+", " ", collapsed).strip()


def _contains_normalized_phrase(text: str, phrase: str) -> bool:
    if text == phrase:
        return True
    return f" {phrase} " in f" {text} "


_RECOGNIZED_CLASS_TERMS = {_normalize_term(term) for term in _RAW_RECOGNIZED_CLASS_TERMS}
