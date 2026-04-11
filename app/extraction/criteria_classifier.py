import re

from app.extraction.negation_resolver import LogicGrouper, NegationResolver, TemporalParser
from app.extraction.quantitative_parser import QuantitativeParser
from app.extraction.types import ClassifiedCriterion, Entity

_AGE_PATTERN = re.compile(r"\bage\b", re.I)
_LINE_PATTERN = re.compile(r"\b(?:line|first.line|second.line|third.line|prior\s+line)\b", re.I)
_CNS_PATTERN = re.compile(r"\b(?:cns|brain|central nervous system|leptomeningeal)\b", re.I)
_STAGE_PATTERN = re.compile(r"\b(?:stage\s+[IViv]+|unresectable|metastatic|locally advanced)\b", re.I)
_HISTOLOGY_PATTERN = re.compile(r"\b(?:adenocarcinoma|squamous|histolog|histopatholog)\b", re.I)
_MOLECULAR_PATTERN = re.compile(r"\b(?:mutation|rearrangement|amplification|fusion|alteration|wild.?type)\b", re.I)
_CONCOMITANT_PATTERN = re.compile(
    r"\b(?:concurrent|concomitant)\b.*\b(?:medications?|drugs?|treatments?|inhibitors?|inducers?|substrates?)\b",
    re.I,
)
_COMPLEXITY_SIGNALS = re.compile(r"\b(?:unless|except|provided that|other than)\b", re.I)
_BIOMARKER_QUALIFIER = re.compile(r"(positive|negative|high|low|overexpression|amplified)", re.I)


class RuleBasedClassifier:
    """Stage 3: Rule-based criteria classification (MVP implementation)."""

    def __init__(self):
        self._quant = QuantitativeParser()
        self._negation = NegationResolver()
        self._temporal = TemporalParser()
        self._logic = LogicGrouper()

    def classify(self, criterion_text: str, entities: list[Entity]) -> ClassifiedCriterion:
        # Complexity check — flag complex criteria for review
        is_complex = bool(_COMPLEXITY_SIGNALS.search(criterion_text))
        if is_complex and len(entities) > 1:
            return ClassifiedCriterion(
                original_text=criterion_text,
                type="inclusion",
                category=self._assign_category(criterion_text, entities),
                parse_status="partial",
                entities=entities,
                confidence=0.3,
                review_required=True,
                review_reason="complex_criteria",
            )

        # No entities → unparsed
        if not entities:
            category = self._assign_category_from_text(criterion_text)
            return ClassifiedCriterion(
                original_text=criterion_text,
                type="inclusion",
                category=category,
                parse_status="unparsed" if category == "other" else "partial",
                confidence=0.0 if category == "other" else 0.3,
                review_required=True,
                review_reason="complex_criteria",
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
        if _STAGE_PATTERN.search(text):
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
        if _MOLECULAR_PATTERN.search(text):
            return "molecular_alteration"
        if _CONCOMITANT_PATTERN.search(text):
            return "concomitant_medication"
        if "PERF_SCALE" in labels:
            return "performance_status"
        if "BIOMARKER" in labels:
            return "biomarker"
        if "LAB_TEST" in labels:
            return "lab_value"
        if "DRUG" in labels:
            return "prior_therapy"
        if "DISEASE" in labels:
            return "diagnosis"
        return self._assign_category_from_text(text)

    def _assign_category_from_text(self, text: str) -> str:
        """Fallback: classify by text patterns when no entities."""
        if _AGE_PATTERN.search(text):
            return "age"
        if _CNS_PATTERN.search(text):
            return "cns_metastases"
        if _STAGE_PATTERN.search(text):
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
        if _MOLECULAR_PATTERN.search(text):
            return "molecular_alteration"
        if _CONCOMITANT_PATTERN.search(text):
            return "concomitant_medication"
        if _LINE_PATTERN.search(text):
            return "line_of_therapy"
        if re.search(r"\borgan function\b", text, re.I):
            return "organ_function"
        return "other"
