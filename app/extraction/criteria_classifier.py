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
_STRONG_PRIOR_THERAPY_ANCHOR_PATTERN = re.compile(
    r"\b(?:prior|previous|received|receipt\s+of|progress(?:ed)?\s+on|failed|refractory|after|during|history\s+of)\b",
    re.I,
)
_TARGETED_EXPOSURE_PATTERN = re.compile(
    r"\b(?:received|receiving|treated|treatment|therapy|agent|drug|inhibitor|antibody)\b.*"
    r"\b(?:targeting|targeted|directed\s+against)\b"
    r"|"
    r"\b(?:targeting|targeted|directed\s+against)\b.*"
    r"\b(?:agent|drug|inhibitor|antibody|therapy|treatment)\b",
    re.I,
)
_CONCOMITANT_PATTERN = re.compile(
    r"\b(?:concurrent|concomitant)\b.*\b(?:medications?|drugs?|treatments?|inhibitors?|inducers?|substrates?)\b",
    re.I,
)
_VACCINE_PATTERN = re.compile(
    r"\b(?:live(?:-attenuated)?\s+vaccine|vaccines?)\b",
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
    r"pulmonary illnesses?|primary brain tumors?|primary cns tumors?|uncontrolled (?:infection|diabetes)|"
    r"connective tissue disease|second malignan(?:cy|cies)|additional malignan(?:cy|cies)|"
    r"concurrent malignan(?:cy|cies))\b",
    re.I,
)
_PROCEDURAL_PATTERN = re.compile(
    r"\b(?:archival\s+tumou?r\s+tissue|newly\s+obtained\s+biopsy|provided\s+tissue\s+prior\s+to|"
    r"recovered\s+from\s+major\s+surgery|major\s+surgery|surgical\s+complications?)\b",
    re.I,
)
_ADMINISTRATIVE_CONSENT_POSITIVE_PATTERN = re.compile(
    r"\b(?:provide|provided|give|given|sign|signed|understand|understood)\b.{0,40}\binformed consent\b"
    r"|\bable to consent\b"
    r"|\bwilling and able\b.{0,50}\binformed consent\b",
    re.I,
)
_ADMINISTRATIVE_CONSENT_NEGATIVE_PATTERN = re.compile(
    r"\b(?:unable|cannot|can't|inability)\b.{0,40}\b(?:consent|provide informed consent|sign informed consent)\b"
    r"|\badults?\s+unable\s+to\s+consent\b"
    r"|\binability to provide informed consent\b",
    re.I,
)
_ADMINISTRATIVE_PROTOCOL_POSITIVE_PATTERN = re.compile(
    r"\b(?:willing and able|able|ability|willing(?:ness)?)\b.{0,70}\b(?:comply|adhere|follow)\b.{0,70}"
    r"\b(?:protocol|study procedures?|scheduled visits?|treatment plan|laboratory tests?)\b",
    re.I,
)
_ADMINISTRATIVE_PROTOCOL_NEGATIVE_PATTERN = re.compile(
    r"\b(?:unable|cannot|can't|inability|unwilling(?:ness)?)\b.{0,70}\b(?:comply|adhere|follow)\b.{0,70}"
    r"\b(?:protocol|study procedures?|scheduled visits?|treatment plan|laboratory tests?)\b",
    re.I,
)
_BEHAVIORAL_CLAUSTROPHOBIA_PATTERN = re.compile(r"\bclaustrophobi(?:a|c)\b", re.I)
_BEHAVIORAL_MOTION_PATTERN = re.compile(
    r"\b(?:motion intolerance|unable to remain still|cannot remain still|unable to lie still|cannot lie still|"
    r"unable to tolerate (?:mri|pet|scan|imaging)|inability to tolerate (?:mri|pet|scan|imaging)|"
    r"dyspnea precluding the ability to follow breath-hold instructions)\b",
    re.I,
)
_REPRODUCTIVE_PATTERN = re.compile(
    r"\b(?:pregnan(?:cy|t)|non[- ]pregnant|negative pregnancy test|breastfeeding|lactating|nursing)\b",
    re.I,
)
_DEVICE_PATTERN = re.compile(
    r"\b(?:contraindication to mri|mri contraindication|mr[- ]?(?:unsafe|incompatible)|pacemakers?|"
    r"defibrillators?|cochlear implants?|aneurysm clips?|metallic implants?|implantable devices?|"
    r"neurostimulators?|mr devices?)\b",
    re.I,
)
_CORTICOSTEROID_PATTERN = re.compile(
    r"\b(?:systemic\s+corticosteroids?|corticosteroids?|systemic\s+steroids?|glucocorticoids?|"
    r"prednisone|dexamethasone|methylprednisolone|prednisolone)\b",
    re.I,
)
_EXPLICIT_DIAGNOSIS_PATTERN = re.compile(
    r"\b(?:diagnosis|diagnosed with)\b",
    re.I,
)
_CONFIRMED_DISEASE_PATTERN = re.compile(
    r"\b(?:confirmed|histologically|cytologically|pathologically)\b",
    re.I,
)
_DISEASE_ENUMERATION_HINT_PATTERN = re.compile(
    r"\b(?:solid tumou?rs?|cancers?|carcinomas?|malignan(?:cy|cies)|neoplasms?)\b",
    re.I,
)
_NUMERIC_STAGE_PATTERN = re.compile(
    r"\bstage\s+[0-9ivx]+[a-c]?(?:\s+or\s+[0-9ivx]+[a-c]?)?\b",
    re.I,
)
_TEXT_STAGE_VALUE_PATTERN = re.compile(
    r"\b(stage\s+[0-9ivx]+[a-c]?(?:\s+or\s+[0-9ivx]+[a-c]?)?|unresectable|metastatic|locally advanced)\b",
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
                text_category = self._assign_category_from_text(criterion_text)
                return ClassifiedCriterion(
                    original_text=criterion_text,
                    type="inclusion",
                    category=text_category,
                    value_text=self._semantic_value_text(text_category, criterion_text),
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
                value_text=self._semantic_value_text(category, criterion_text),
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
        if not value_text:
            value_text = self._semantic_value_text(category, criterion_text)

        if category == "concomitant_medication" and _VACCINE_PATTERN.search(criterion_text):
            return ClassifiedCriterion(
                original_text=criterion_text,
                type="inclusion",
                category=category,
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
        if self._is_diagnosis_primary(text, entities):
            return "diagnosis"
        if self._administrative_value(text):
            return "administrative_requirement"
        if self._behavioral_value(text):
            return "behavioral_constraint"
        if self._reproductive_value(text):
            return "reproductive_status"
        if self._device_value(text):
            return "device_constraint"
        if _CNS_PATTERN.search(text):
            return "cns_metastases"
        if _LINE_PATTERN.search(text):
            return "line_of_therapy"
        if _PROCEDURAL_PATTERN.search(text):
            return "procedural_requirement"
        if "BIOMARKER" in labels and _MOLECULAR_PATTERN.search(text):
            return "molecular_alteration"
        if _CURRENT_CONDITION_PATTERN.search(text):
            return "diagnosis"
        if "BIOMARKER" in labels and _TARGETED_EXPOSURE_PATTERN.search(text):
            return "prior_therapy"
        if _CORTICOSTEROID_PATTERN.search(text):
            return "concomitant_medication"
        if _PRIOR_THERAPY_TEXT_PATTERN.search(text):
            return "prior_therapy"
        if "DRUG" in labels:
            return "concomitant_medication" if _CORTICOSTEROID_PATTERN.search(text) else "prior_therapy"
        if _STAGE_PATTERN.search(text):
            if _NUMERIC_STAGE_PATTERN.search(text) or _TNM_STAGE_PATTERN.search(text):
                return "disease_stage"
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
        if _VACCINE_PATTERN.search(text):
            return "concomitant_medication"
        if _CONCOMITANT_PATTERN.search(text) or _CYP_RESTRICTION_PATTERN.search(text):
            return "concomitant_medication"
        if "PERF_SCALE" in labels:
            return "performance_status"
        if "BIOMARKER" in labels:
            return "biomarker"
        if _MOLECULAR_PATTERN.search(text):
            return "molecular_alteration"
        if "LAB_TEST" in labels:
            return "lab_value"
        if "DISEASE" in labels:
            return "diagnosis"
        return self._assign_category_from_text(text)

    def _has_specific_disease_phrase(self, entities: list[Entity]) -> bool:
        for entity in entities:
            if entity.label != "DISEASE":
                continue
            source = entity.expanded_text or entity.text
            tokens = re.findall(r"[a-z0-9]+", source.casefold())
            if len(tokens) >= 3:
                return True
        return False

    def _assign_category_from_text(self, text: str) -> str:
        """Fallback: classify by text patterns when no entities."""
        if _AGE_PATTERN.search(text):
            return "age"
        if self._administrative_value(text):
            return "administrative_requirement"
        if self._behavioral_value(text):
            return "behavioral_constraint"
        if self._reproductive_value(text):
            return "reproductive_status"
        if self._device_value(text):
            return "device_constraint"
        if _CNS_PATTERN.search(text):
            return "cns_metastases"
        if _PROCEDURAL_PATTERN.search(text):
            return "procedural_requirement"
        if _CURRENT_CONDITION_PATTERN.search(text):
            return "diagnosis"
        if _STAGE_PATTERN.search(text):
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
        if _VACCINE_PATTERN.search(text):
            return "concomitant_medication"
        if _CORTICOSTEROID_PATTERN.search(text):
            return "concomitant_medication"
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
        if category in {
            "diagnosis",
            "cns_metastases",
            "disease_stage",
            "procedural_requirement",
            "administrative_requirement",
            "behavioral_constraint",
            "reproductive_status",
            "device_constraint",
        }:
            return category, "parsed", 0.6, False, None
        if category == "concomitant_medication" and _VACCINE_PATTERN.search(text):
            return category, "partial", 0.3, True, "complex_criteria"
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

    def _is_diagnosis_primary(self, text: str, entities: list[Entity]) -> bool:
        disease_entities = [entity for entity in entities if entity.label == "DISEASE"]
        if not disease_entities:
            return False
        if _NUMERIC_STAGE_PATTERN.search(text) or _TNM_STAGE_PATTERN.search(text):
            return False
        if any(entity.label == "BIOMARKER" for entity in entities):
            return False
        if _CURRENT_CONDITION_PATTERN.search(text):
            return True
        if _EXPLICIT_DIAGNOSIS_PATTERN.search(text):
            return True
        if len(disease_entities) >= 2 and not _STRONG_PRIOR_THERAPY_ANCHOR_PATTERN.search(text):
            return True
        if (
            len(disease_entities) >= 1
            and _DISEASE_ENUMERATION_HINT_PATTERN.search(text)
            and not _STRONG_PRIOR_THERAPY_ANCHOR_PATTERN.search(text)
        ):
            return True
        return False

    def _administrative_value(self, text: str) -> str | None:
        if _ADMINISTRATIVE_CONSENT_NEGATIVE_PATTERN.search(text):
            return "can_consent:false"
        if _ADMINISTRATIVE_CONSENT_POSITIVE_PATTERN.search(text):
            return "can_consent:true"
        if _ADMINISTRATIVE_PROTOCOL_NEGATIVE_PATTERN.search(text):
            return "protocol_compliant:false"
        if _ADMINISTRATIVE_PROTOCOL_POSITIVE_PATTERN.search(text):
            return "protocol_compliant:true"
        return None

    def _behavioral_value(self, text: str) -> str | None:
        if _BEHAVIORAL_CLAUSTROPHOBIA_PATTERN.search(text):
            return "claustrophobic:true"
        if _BEHAVIORAL_MOTION_PATTERN.search(text):
            return "motion_intolerant:true"
        return None

    def _reproductive_value(self, text: str) -> str | None:
        if not _REPRODUCTIVE_PATTERN.search(text):
            return None
        if re.search(r"\b(?:non[- ]pregnant|negative pregnancy test)\b", text, re.I):
            return "pregnant:false"
        if re.search(r"\b(?:pregnan(?:cy|t))\b", text, re.I):
            return "pregnant:true"
        return None

    def _device_value(self, text: str) -> str | None:
        if _DEVICE_PATTERN.search(text):
            return "mr_device_present:true"
        return None

    def _semantic_value_text(self, category: str, text: str) -> str | None:
        if category == "administrative_requirement":
            return self._administrative_value(text)
        if category == "behavioral_constraint":
            return self._behavioral_value(text)
        if category == "reproductive_status":
            return self._reproductive_value(text)
        if category == "device_constraint":
            return self._device_value(text)
        if category == "disease_stage":
            match = _TEXT_STAGE_VALUE_PATTERN.search(text)
            if match:
                return match.group(1).lower()
        return None

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
