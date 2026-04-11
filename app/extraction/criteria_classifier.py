import re

from app.extraction.negation_resolver import LogicGrouper, NegationResolver, TemporalParser
from app.extraction.quantitative_parser import QuantitativeParser
from app.extraction.types import ClassifiedCriterion, Entity, QuantitativeValue

_AGE_PATTERN = re.compile(r"\b(?:age|years?\s+old)\b", re.I)
_LINE_PATTERN = re.compile(r"\b(?:line|first.line|second.line|third.line|prior\s+line)\b", re.I)
_CNS_PATTERN = re.compile(r"\b(?:cns|brain|central nervous system|leptomeningeal)\b", re.I)
_STAGE_PATTERN = re.compile(r"\b(?:stage\s+[IViv]+|unresectable|metastatic|locally advanced)\b", re.I)
_TNM_STAGE_PATTERN = re.compile(r"\b(?:[tcnm][0-4](?:mi|[a-c])?)\b", re.I)
_HISTOLOGY_PATTERN = re.compile(r"\b(?:adenocarcinoma|squamous|histolog|histopatholog)\b", re.I)
_MOLECULAR_PATTERN = re.compile(
    r"(?:\b(?:mutation|rearrangement|amplification|fusion|alteration|wild.?type)\b|"
    r"\b(?:genetic|genomic)\s+variants?\b)",
    re.I,
)
_PRIOR_THERAPY_TEXT_PATTERN = re.compile(
    r"\b(?:prior\s+treatment|prior\s+therapy|chemotherap(?:y|ies)|radiation(?:\s+therapy)?|immunotherap(?:y|ies)|"
    r"endocrine\s+therapy|hormonal\s+therapy|targeted\s+therapy|systemic\s+therapy|"
    r"biologic(?:al)?\s+therapy)\b",
    re.I,
)
_CONCOMITANT_PATTERN = re.compile(
    r"\b(?:concurrent|concomitant)\b.*\b(?:medications?|drugs?|treatments?|inhibitors?|inducers?|substrates?)\b",
    re.I,
)
_CYP_RESTRICTION_PATTERN = re.compile(
    r"(?:\bcyp[0-9a-z-]+\b.*\b(?:inhibitors?|inducers?)\b|\b(?:inhibitors?|inducers?)\b.*\bcyp[0-9a-z-]+\b)",
    re.I,
)
_HYPERSENSITIVITY_PATTERN = re.compile(
    r"\b(?:hypersensitiv(?:ity|e)|allerg(?:y|ic)|anaphylaxis|intoleran(?:ce|t))\b",
    re.I,
)
_SEX_ONLY_PATTERN = re.compile(
    r"\b(female|male)\s+(?:patients?|subjects?|participants?)\s+only\b",
    re.I,
)
_ORGAN_FUNCTION_COMPLEXITY_PATTERN = re.compile(
    r"\b(?:as\s+determined\s+by|per\s+institutional|investigator)\b",
    re.I,
)
_ORGAN_FUNCTION_PATTERN = re.compile(
    r"\b(?:organ function|renal function|kidney function|hepatic function|liver function|"
    r"hematologic function|haematologic function|bone marrow function)\b",
    re.I,
)
_CURRENT_CONDITION_PATTERN = re.compile(
    r"\b(?:active infection|immunodeficiency|pneumonitis|interstitial lung disease|"
    r"inflammatory bowel disease|cardiovascular disorder|cerebrovascular disease|"
    r"pulmonary illnesses?)\b",
    re.I,
)
_COMPLEXITY_SIGNALS = re.compile(
    r"\b(?:unless|except|provided that|other than|whichever\s+is\s+(?:longer|shorter)|"
    r"including\s+but\s+not\s+limited\s+to)\b",
    re.I,
)
_BIOMARKER_QUALIFIER = re.compile(r"(positive|negative|high|low|overexpression|amplified)", re.I)
_INCLUDING_PATTERN = re.compile(r"\bincluding\b", re.I)
_AT_LEAST_COUNT_PATTERN = re.compile(r"\bat\s+least\s+[\d.]+\b", re.I)
_ALLOWANCE_PATTERN = re.compile(r"\b(?:can\s+be\s+included|eligible)\b", re.I)


class RuleBasedClassifier:
    """Stage 3: Rule-based criteria classification (MVP implementation)."""

    def __init__(self):
        self._quant = QuantitativeParser()
        self._negation = NegationResolver()
        self._temporal = TemporalParser()
        self._logic = LogicGrouper()

    def classify(self, criterion_text: str, entities: list[Entity]) -> ClassifiedCriterion:
        labels = {entity.label for entity in entities}
        category_hint = (
            self._assign_category(criterion_text, entities)
            if entities
            else self._assign_category_from_text(criterion_text)
        )
        has_mixed_stage_biomarker = self._has_mixed_stage_biomarker_signals(
            criterion_text,
            labels,
        )
        has_nested_therapy_requirements = self._has_nested_therapy_requirements(
            criterion_text,
            category_hint,
        )
        has_cns_exception_allowance = self._has_cns_exception_allowance(
            criterion_text,
            category_hint,
        )

        # Complexity check — flag complex criteria for review
        is_complex = bool(_COMPLEXITY_SIGNALS.search(criterion_text))
        if (
            has_mixed_stage_biomarker
            or has_nested_therapy_requirements
            or has_cns_exception_allowance
            or (
                is_complex and (
                    not entities
                    or len(entities) > 1
                    or category_hint in {"concomitant_medication", "molecular_alteration"}
                )
            )
        ):
            neg_result = self._negation.resolve(criterion_text, entities)
            temporal = self._temporal.parse(neg_result.exception_text or criterion_text)
            logic = self._logic.detect(criterion_text)
            return ClassifiedCriterion(
                original_text=criterion_text,
                type="inclusion",
                category=category_hint,
                parse_status="partial",
                entities=entities,
                negated=neg_result.negated,
                timeframe_operator=temporal.operator if temporal else None,
                timeframe_value=temporal.value if temporal else None,
                timeframe_unit=temporal.unit if temporal else None,
                logic_group_id=logic.group_id,
                logic_operator=logic.operator,
                confidence=0.3,
                review_required=True,
                review_reason="complex_criteria",
            )

        # No entities → unparsed
        if not entities:
            neg_result = self._negation.resolve(criterion_text, [])
            if neg_result.has_exception:
                exception_temporal = self._temporal.parse(neg_result.exception_text or "")
                return ClassifiedCriterion(
                    original_text=criterion_text,
                    type="inclusion",
                    category=self._assign_category_from_text(criterion_text),
                    parse_status="partial",
                    negated=neg_result.negated,
                    timeframe_operator=exception_temporal.operator if exception_temporal else None,
                    timeframe_value=exception_temporal.value if exception_temporal else None,
                    timeframe_unit=exception_temporal.unit if exception_temporal else None,
                    confidence=0.3,
                    review_required=True,
                    review_reason="complex_criteria",
                )
            sex_match = _SEX_ONLY_PATTERN.search(criterion_text)
            if sex_match:
                return ClassifiedCriterion(
                    original_text=criterion_text,
                    type="inclusion",
                    category="other",
                    parse_status="partial",
                    value_text=sex_match.group(1).lower(),
                    raw_expression=criterion_text,
                    confidence=0.6,
                    review_required=False,
                )
            category, parse_status, confidence, review_required, review_reason = self._classify_text_only(
                criterion_text
            )
            return ClassifiedCriterion(
                original_text=criterion_text,
                type="inclusion",
                category=category,
                parse_status=parse_status,
                confidence=confidence,
                review_required=review_required,
                review_reason=review_reason,
            )

        # Negation
        neg_result = self._negation.resolve(criterion_text, entities)

        # Temporal
        temporal = self._temporal.parse(criterion_text)

        # Logic
        logic = self._logic.detect(criterion_text)

        # Quantitative — try measure entities, then cardinal, then full text
        quant = None
        for e in entities:
            if e.label in ("MEASURE", "CARDINAL"):
                quant = self._quant.parse(e.text, entities)
                if quant:
                    break
        if not quant:
            quant = self._quant.parse(criterion_text, entities)

        # Category
        category = self._assign_category(criterion_text, entities)

        if category == "age" and not quant and temporal and temporal.unit == "years":
            quant = self._age_quant_from_temporal(temporal, criterion_text)
            if quant:
                temporal = None

        # Biomarker qualifier
        value_text = None
        if category == "biomarker":
            qual_match = _BIOMARKER_QUALIFIER.search(criterion_text)
            if qual_match:
                value_text = qual_match.group(1).lower()

        return ClassifiedCriterion(
            original_text=criterion_text,
            type="inclusion",
            category=category,
            parse_status="parsed",
            entities=entities,
            operator=quant.operator if quant else None,
            value_low=quant.value_low if quant else None,
            value_high=quant.value_high if quant else None,
            value_text=value_text or (quant.value_text if quant else None),
            unit=quant.unit if quant else None,
            raw_expression=quant.raw_expression if quant else None,
            negated=neg_result.negated,
            timeframe_operator=temporal.operator if temporal else None,
            timeframe_value=temporal.value if temporal else None,
            timeframe_unit=temporal.unit if temporal else None,
            logic_group_id=logic.group_id,
            logic_operator=logic.operator,
            confidence=0.85,
        )

    def _assign_category(self, text: str, entities: list[Entity]) -> str:
        labels = {e.label for e in entities}

        if _AGE_PATTERN.search(text) or ("MEASURE" in labels and "year" in text.lower()):
            return "age"
        if _CNS_PATTERN.search(text):
            return "cns_metastases"
        if _LINE_PATTERN.search(text):
            return "line_of_therapy"
        if "DISEASE" in labels or _CURRENT_CONDITION_PATTERN.search(text):
            return "diagnosis"
        if _PRIOR_THERAPY_TEXT_PATTERN.search(text):
            return "prior_therapy"
        if "DRUG" in labels:
            return "prior_therapy"
        if _STAGE_PATTERN.search(text):
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
        if _MOLECULAR_PATTERN.search(text):
            return "molecular_alteration"
        if _CONCOMITANT_PATTERN.search(text) or _CYP_RESTRICTION_PATTERN.search(text):
            return "concomitant_medication"
        if "PERF_SCALE" in labels:
            return "performance_status"
        if "BIOMARKER" in labels:
            return "biomarker"
        if "LAB_TEST" in labels:
            return "lab_value"
        if "DISEASE" in labels:
            return "diagnosis"
        return self._assign_category_from_text(text)

    def _assign_category_from_text(self, text: str) -> str:
        """Fallback: classify by text patterns when no entities."""
        if _AGE_PATTERN.search(text):
            return "age"
        if _CNS_PATTERN.search(text):
            return "cns_metastases"
        if _CURRENT_CONDITION_PATTERN.search(text):
            return "diagnosis"
        if _STAGE_PATTERN.search(text):
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
        if _MOLECULAR_PATTERN.search(text):
            return "molecular_alteration"
        if _CONCOMITANT_PATTERN.search(text) or _CYP_RESTRICTION_PATTERN.search(text):
            return "concomitant_medication"
        if _LINE_PATTERN.search(text):
            return "line_of_therapy"
        if _PRIOR_THERAPY_TEXT_PATTERN.search(text):
            return "prior_therapy"
        if _ORGAN_FUNCTION_PATTERN.search(text):
            return "organ_function"
        return "other"

    def _classify_text_only(self, text: str) -> tuple[str, str, float, bool, str | None]:
        category = self._assign_category_from_text(text)
        if category == "histology":
            return category, "parsed", 0.6, False, None
        if category == "concomitant_medication":
            return category, "parsed", 0.6, False, None
        if category == "organ_function" and not _ORGAN_FUNCTION_COMPLEXITY_PATTERN.search(text):
            return category, "parsed", 0.6, False, None
        if _HYPERSENSITIVITY_PATTERN.search(text):
            return category, "partial", 0.6, False, None
        if category == "other":
            return category, "unparsed", 0.0, True, "complex_criteria"
        return category, "partial", 0.3, True, "complex_criteria"

    def _has_mixed_stage_biomarker_signals(self, text: str, labels: set[str]) -> bool:
        has_biomarker_signal = "BIOMARKER" in labels or _MOLECULAR_PATTERN.search(text)
        has_stage_signal = _STAGE_PATTERN.search(text) or _TNM_STAGE_PATTERN.search(text)
        return bool(has_biomarker_signal and has_stage_signal)

    def _has_nested_therapy_requirements(self, text: str, category_hint: str) -> bool:
        if category_hint not in {"prior_therapy", "line_of_therapy"}:
            return False
        if not _INCLUDING_PATTERN.search(text):
            return False
        return len(_AT_LEAST_COUNT_PATTERN.findall(text)) >= 2

    def _has_cns_exception_allowance(self, text: str, category_hint: str) -> bool:
        if category_hint != "cns_metastases":
            return False
        return bool(_ALLOWANCE_PATTERN.search(text) and _CNS_PATTERN.search(text))

    def _age_quant_from_temporal(
        self, temporal, criterion_text: str
    ) -> QuantitativeValue | None:
        op = {
            "at_least": "gte",
            "no_more": "lte",
        }.get(temporal.operator)
        if not op:
            return None
        return QuantitativeValue(
            operator=op,
            value_low=temporal.value,
            unit=temporal.unit,
            raw_expression=criterion_text,
        )
