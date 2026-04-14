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
    r"endocrine\s+therapy|hormonal\s+therapy|targeted\s+therap(?:y|ies)|systemic\s+therapy|"
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
_LIVE_VACCINE_PATTERN = re.compile(
    r"\b(?:live(?:\s+or\s+live-attenuated)?|live-attenuated)\s+vaccines?\b",
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
_DISEASE_STATUS_PATTERN = re.compile(
    r"\b(?:documented\s+disease\s+progression|disease\s+progression|progression|progressed|refractory|"
    r"relapsed|recurrent|recurrence)\b",
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
_ADMINISTRATIVE_PARTICIPATION_POSITIVE_PATTERN = re.compile(
    r"\b(?:willing and able|able|ability|willing(?:ness)?)\b.{0,80}\b(?:participate|complete|undergo|attend)\b.{0,80}"
    r"\b(?:study evaluations?|evaluations?|study procedures?|procedures?|visits?)\b",
    re.I,
)
_ADMINISTRATIVE_PARTICIPATION_NEGATIVE_PATTERN = re.compile(
    r"\b(?:unable|cannot|can't|inability|unwilling(?:ness)?)\b.{0,80}\b(?:participate|complete|undergo|attend)\b.{0,80}"
    r"\b(?:study evaluations?|evaluations?|study procedures?|procedures?|visits?)\b",
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
_IMMUNOSUPPRESSIVE_THERAPY_PATTERN = re.compile(
    r"\b(?:immunosuppressive\s+therapy|immunosuppressive\s+medications?|"
    r"immunosuppressants?|systemic\s+steroid\s+therapy|chronic\s+systemic\s+steroid\s+therapy)\b",
    re.I,
)
_EXPLICIT_DIAGNOSIS_PATTERN = re.compile(
    r"\b(?:diagnosis|diagnosed with)\b",
    re.I,
)
_CONFIRMED_DISEASE_PATTERN = re.compile(
    r"\b(?:confirmed|histologically|cytologically|pathologically|biopsy[- ]confirmed|biopsy)\b",
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
_NSCLC_SUBTYPE_PATTERN = re.compile(r"\bnon[- ]small cell\b", re.I)
_SCLC_SUBTYPE_PATTERN = re.compile(r"\bsmall cell\b", re.I)
_HISTOLOGY_VALUE_PATTERN = re.compile(
    r"\b(?:non[- ]squamous|squamous|adenocarcinoma|histologically confirmed|cytologically confirmed)\b",
    re.I,
)
_SPECIMEN_PATTERNS = (
    (re.compile(r"\b(?:circulating\s+tumou?r\s+deoxyribonucleic\s+acid|ctdna)\b", re.I), "ctDNA"),
    (re.compile(r"\btumou?r\s+tissue\b", re.I), "tumor tissue"),
    (re.compile(r"\bplasma\b", re.I), "plasma"),
    (re.compile(r"\bblood\b", re.I), "blood"),
)
_TESTING_MODALITY_PATTERNS = (
    (re.compile(r"\bnext[- ]generation sequencing\b|\bngs\b", re.I), "next_generation_sequencing"),
    (re.compile(r"\bimmunohistochemistry\b|\bihc\b", re.I), "immunohistochemistry"),
    (re.compile(r"\bpcr\b|\brt-pcr\b", re.I), "polymerase_chain_reaction"),
    (re.compile(r"\bfish\b", re.I), "fluorescence_in_situ_hybridization"),
    (re.compile(r"\bctdna\b", re.I), "liquid_biopsy"),
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
_PHYSIOLOGIC_ALLOWANCE_PATTERN = re.compile(
    r"\bphysiologic(?:al)?(?:\s+replacement)?\s+doses?\b[^.;)]*",
    re.I,
)
_MEDICATION_EXCEPTION_TRUNCATION_PATTERN = re.compile(r"\b(?:which|that|who|when)\b", re.I)


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
        neg_result = self._negation.resolve(criterion_text, entities)
        temporal = self._temporal.parse(criterion_text)
        semantic_details = self._semantic_details(
            category_hint,
            criterion_text,
            entities,
            neg_result=neg_result,
            temporal=temporal,
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
        medication_requires_review = self._requires_medication_review(
            criterion_text,
            category_hint,
            semantic_details,
        )
        medication_structured = (
            category_hint == "concomitant_medication"
            and semantic_details.get("exception_logic") is not None
            and not medication_requires_review
        )

        # Complexity check — flag complex criteria for review
        is_complex = bool(_COMPLEXITY_SIGNALS.search(criterion_text))
        if (
            has_mixed_stage_biomarker
            or has_nested_therapy_requirements
            or has_cns_exception_allowance
            or (
                not medication_structured
                and
                is_complex and (
                    not entities
                    or len(entities) > 1
                    or category_hint == "molecular_alteration"
                    or medication_requires_review
                )
            )
        ):
            logic = self._logic.detect(criterion_text)
            value_text = self._semantic_value_text(category_hint, criterion_text, entities)
            confidence, confidence_factors = self._score_confidence(
                category=category_hint,
                parse_status="partial",
                text=criterion_text,
                entities=entities,
                quant=None,
                temporal=temporal,
                semantic_details=semantic_details,
                value_text=value_text,
            )
            return ClassifiedCriterion(
                original_text=criterion_text,
                type="inclusion",
                category=category_hint,
                primary_semantic_category=category_hint,
                secondary_semantic_tags=semantic_details["secondary_semantic_tags"],
                value_text=value_text,
                parse_status="partial",
                entities=entities,
                negated=neg_result.negated,
                timeframe_operator=temporal.operator if temporal else None,
                timeframe_value=temporal.value if temporal else None,
                timeframe_unit=temporal.unit if temporal else None,
                specimen_type=semantic_details["specimen_type"],
                testing_modality=semantic_details["testing_modality"],
                disease_subtype=semantic_details["disease_subtype"],
                histology_text=semantic_details["histology_text"],
                assay_context=semantic_details["assay_context"],
                exception_logic=semantic_details["exception_logic"],
                exception_entities=semantic_details["exception_entities"],
                allowance_text=semantic_details["allowance_text"],
                logic_group_id=logic.group_id,
                logic_operator=logic.operator,
                confidence=confidence,
                confidence_factors=confidence_factors,
                review_required=True,
                review_reason="complex_criteria",
            )

        # No entities → unparsed
        if not entities:
            if neg_result.has_exception:
                text_category = self._assign_category_from_text(criterion_text)
                semantic_details = self._semantic_details(
                    text_category,
                    criterion_text,
                    [],
                    neg_result=neg_result,
                    temporal=temporal,
                )
                value_text = self._semantic_value_text(text_category, criterion_text, [])
                confidence, confidence_factors = self._score_confidence(
                    category=text_category,
                    parse_status="partial",
                    text=criterion_text,
                    entities=[],
                    quant=None,
                    temporal=temporal,
                    semantic_details=semantic_details,
                    value_text=value_text,
                )
                return ClassifiedCriterion(
                    original_text=criterion_text,
                    type="inclusion",
                    category=text_category,
                    primary_semantic_category=text_category,
                    secondary_semantic_tags=semantic_details["secondary_semantic_tags"],
                    value_text=value_text,
                    parse_status="partial",
                    negated=neg_result.negated,
                    timeframe_operator=temporal.operator if temporal else None,
                    timeframe_value=temporal.value if temporal else None,
                    timeframe_unit=temporal.unit if temporal else None,
                    specimen_type=semantic_details["specimen_type"],
                    testing_modality=semantic_details["testing_modality"],
                    disease_subtype=semantic_details["disease_subtype"],
                    histology_text=semantic_details["histology_text"],
                    assay_context=semantic_details["assay_context"],
                    exception_logic=semantic_details["exception_logic"],
                    exception_entities=semantic_details["exception_entities"],
                    allowance_text=semantic_details["allowance_text"],
                    confidence=confidence,
                    confidence_factors=confidence_factors,
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
                    confidence_factors={"base": 0.6, "structured_components": ["sex_only_text"]},
                    review_required=False,
                )
            category, parse_status, confidence, review_required, review_reason = self._classify_text_only(
                criterion_text
            )
            semantic_details = self._semantic_details(
                category,
                criterion_text,
                [],
                neg_result=neg_result,
                temporal=temporal,
            )
            value_text = self._semantic_value_text(category, criterion_text, [])
            confidence, confidence_factors = self._score_confidence(
                category=category,
                parse_status=parse_status,
                text=criterion_text,
                entities=[],
                quant=None,
                temporal=temporal,
                semantic_details=semantic_details,
                value_text=value_text,
                base_override=confidence,
            )
            return ClassifiedCriterion(
                original_text=criterion_text,
                type="inclusion",
                category=category,
                primary_semantic_category=category,
                secondary_semantic_tags=semantic_details["secondary_semantic_tags"],
                parse_status=parse_status,
                value_text=value_text,
                negated=neg_result.negated,
                timeframe_operator=temporal.operator if temporal else None,
                timeframe_value=temporal.value if temporal else None,
                timeframe_unit=temporal.unit if temporal else None,
                specimen_type=semantic_details["specimen_type"],
                testing_modality=semantic_details["testing_modality"],
                disease_subtype=semantic_details["disease_subtype"],
                histology_text=semantic_details["histology_text"],
                assay_context=semantic_details["assay_context"],
                exception_logic=semantic_details["exception_logic"],
                exception_entities=semantic_details["exception_entities"],
                allowance_text=semantic_details["allowance_text"],
                confidence=confidence,
                confidence_factors=confidence_factors,
                review_required=review_required,
                review_reason=review_reason,
            )

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
        if category != category_hint:
            semantic_details = self._semantic_details(
                category,
                criterion_text,
                entities,
                neg_result=neg_result,
                temporal=temporal,
            )

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
            value_text = self._semantic_value_text(category, criterion_text, entities)

        confidence, confidence_factors = self._score_confidence(
            category=category,
            parse_status="parsed",
            text=criterion_text,
            entities=entities,
            quant=quant,
            temporal=temporal,
            semantic_details=semantic_details,
            value_text=value_text,
        )

        return ClassifiedCriterion(
            original_text=criterion_text,
            type="inclusion",
            category=category,
            primary_semantic_category=category,
            secondary_semantic_tags=semantic_details["secondary_semantic_tags"],
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
            specimen_type=semantic_details["specimen_type"],
            testing_modality=semantic_details["testing_modality"],
            disease_subtype=semantic_details["disease_subtype"],
            histology_text=semantic_details["histology_text"],
            assay_context=semantic_details["assay_context"],
            exception_logic=semantic_details["exception_logic"],
            exception_entities=semantic_details["exception_entities"],
            allowance_text=semantic_details["allowance_text"],
            logic_group_id=logic.group_id,
            logic_operator=logic.operator,
            confidence=confidence,
            confidence_factors=confidence_factors,
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
        if _VACCINE_PATTERN.search(text):
            return "concomitant_medication"
        if _CONCOMITANT_PATTERN.search(text) or _CYP_RESTRICTION_PATTERN.search(text):
            return "concomitant_medication"
        if _CORTICOSTEROID_PATTERN.search(text) or _IMMUNOSUPPRESSIVE_THERAPY_PATTERN.search(text):
            return "concomitant_medication"
        if _DISEASE_STATUS_PATTERN.search(text) and not ("DRUG" in labels or _PRIOR_THERAPY_TEXT_PATTERN.search(text)):
            return "disease_status"
        if "BIOMARKER" in labels and _MOLECULAR_PATTERN.search(text):
            return "molecular_alteration"
        if _CURRENT_CONDITION_PATTERN.search(text):
            return "diagnosis"
        if "BIOMARKER" in labels and _TARGETED_EXPOSURE_PATTERN.search(text):
            return "prior_therapy"
        if _PRIOR_THERAPY_TEXT_PATTERN.search(text):
            return "prior_therapy"
        if "DRUG" in labels:
            return "prior_therapy"
        if _STAGE_PATTERN.search(text):
            if _NUMERIC_STAGE_PATTERN.search(text) or _TNM_STAGE_PATTERN.search(text):
                return "disease_stage"
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
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
        if _DISEASE_STATUS_PATTERN.search(text) and not _PRIOR_THERAPY_TEXT_PATTERN.search(text):
            return "disease_status"
        if _CURRENT_CONDITION_PATTERN.search(text):
            return "diagnosis"
        if _STAGE_PATTERN.search(text):
            return "disease_stage"
        if _HISTOLOGY_PATTERN.search(text):
            return "histology"
        if _VACCINE_PATTERN.search(text):
            return "concomitant_medication"
        if _CORTICOSTEROID_PATTERN.search(text) or _IMMUNOSUPPRESSIVE_THERAPY_PATTERN.search(text):
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
            "disease_status",
            "procedural_requirement",
            "administrative_requirement",
            "behavioral_constraint",
            "reproductive_status",
            "device_constraint",
        }:
            return category, "parsed", 0.6, False, None
        if category == "concomitant_medication":
            if _COMPLEXITY_SIGNALS.search(text) and not (
                _VACCINE_PATTERN.search(text)
                or _CORTICOSTEROID_PATTERN.search(text)
                or _CYP_RESTRICTION_PATTERN.search(text)
            ):
                return category, "partial", 0.3, True, "complex_criteria"
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
        if _CONFIRMED_DISEASE_PATTERN.search(text) and not _STRONG_PRIOR_THERAPY_ANCHOR_PATTERN.search(text):
            return True
        if len(disease_entities) >= 2 and not _STRONG_PRIOR_THERAPY_ANCHOR_PATTERN.search(text):
            return True
        if (
            len(disease_entities) >= 1
            and _DISEASE_ENUMERATION_HINT_PATTERN.search(text)
            and (
                not _STRONG_PRIOR_THERAPY_ANCHOR_PATTERN.search(text)
                or _CONFIRMED_DISEASE_PATTERN.search(text)
            )
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
        if _ADMINISTRATIVE_PARTICIPATION_NEGATIVE_PATTERN.search(text):
            return "protocol_compliant:false"
        if _ADMINISTRATIVE_PARTICIPATION_POSITIVE_PATTERN.search(text):
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

    def _semantic_value_text(self, category: str, text: str, entities: list[Entity] | None = None) -> str | None:
        if category == "administrative_requirement":
            return self._administrative_value(text)
        if category == "behavioral_constraint":
            return self._behavioral_value(text)
        if category == "reproductive_status":
            return self._reproductive_value(text)
        if category == "device_constraint":
            return self._device_value(text)
        if category in {"prior_therapy", "line_of_therapy"}:
            return self._infer_therapy_base_text(text, entities or [])
        if category == "concomitant_medication":
            return self._infer_medication_base_text(text)
        if category == "disease_status":
            match = _DISEASE_STATUS_PATTERN.search(text)
            if match:
                return match.group(0).lower()
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

    def _requires_medication_review(
        self,
        text: str,
        category_hint: str,
        semantic_details: dict[str, object],
    ) -> bool:
        if category_hint != "concomitant_medication":
            return False
        if "whichever is longer" in text.casefold() or "whichever is shorter" in text.casefold():
            return True
        exception_logic = semantic_details.get("exception_logic")
        if not exception_logic:
            return False
        if (
            exception_logic.get("mode") == "prohibited_with_exception"
            and not semantic_details.get("exception_entities")
        ):
            return True
        return False

    def _medication_semantics(
        self,
        text: str,
        entities: list[Entity],
        *,
        neg_result,
        temporal,
    ) -> tuple[dict[str, object] | None, list[str], str | None]:
        base_entities = self._medication_base_entities(text, entities, neg_result)
        if not base_entities and not (
            _VACCINE_PATTERN.search(text)
            or _CORTICOSTEROID_PATTERN.search(text)
            or _CYP_RESTRICTION_PATTERN.search(text)
        ):
            return None, [], None

        exception_entities = self._medication_exception_entities(text, entities, neg_result)
        allowance_text = self._medication_allowance_text(text, neg_result)
        if not base_entities:
            inferred = self._infer_medication_base_text(text)
            if inferred:
                base_entities = [inferred]

        logic_mode = "restriction"
        if temporal and base_entities:
            logic_mode = "washout_window"
        if exception_entities:
            logic_mode = "prohibited_with_exception"
        if allowance_text:
            logic_mode = "prohibited_with_allowance"

        if not base_entities and not exception_entities and not allowance_text:
            return None, [], None

        return (
            {
                "mode": logic_mode,
                "base_entities": base_entities,
                "has_timeframe": temporal is not None,
                "exception_text": neg_result.exception_text if neg_result and neg_result.exception_text else None,
            },
            exception_entities,
            allowance_text,
        )

    def _medication_base_entities(self, text: str, entities: list[Entity], neg_result) -> list[str]:
        exception_start = None
        if neg_result and neg_result.exception_text:
            cue_match = re.search(r"\b(unless|except|provided that|other than)\b", text, re.I)
            if cue_match:
                exception_start = cue_match.start()

        values: list[str] = []
        for entity in entities:
            if entity.label != "DRUG":
                continue
            if exception_start is not None and entity.start >= exception_start:
                continue
            normalized = _clean_medication_phrase(entity.expanded_text or entity.text)
            if normalized and normalized not in values:
                values.append(normalized)

        if values:
            return values

        inferred = self._infer_medication_base_text(text)
        return [inferred] if inferred else []

    def _infer_medication_base_text(self, text: str) -> str | None:
        live_vaccine = _LIVE_VACCINE_PATTERN.search(text) or _VACCINE_PATTERN.search(text)
        if live_vaccine:
            return _clean_medication_phrase(live_vaccine.group(0))
        if _CYP_RESTRICTION_PATTERN.search(text):
            return "cyp3a4 inhibitors/inducers"
        corticosteroid_match = _CORTICOSTEROID_PATTERN.search(text)
        if corticosteroid_match:
            return _clean_medication_phrase(corticosteroid_match.group(0))
        immunosuppressive_match = _IMMUNOSUPPRESSIVE_THERAPY_PATTERN.search(text)
        if immunosuppressive_match:
            return _clean_medication_phrase(immunosuppressive_match.group(0))
        return None

    def _infer_therapy_base_text(self, text: str, entities: list[Entity]) -> str | None:
        therapy_match = re.search(
            r"\b(?:targeted\s+therap(?:y|ies)|trastuzumab-containing\s+treatments?)\b",
            text,
            re.I,
        )
        if therapy_match:
            return _clean_medication_phrase(therapy_match.group(0))

        for entity in entities:
            if entity.label == "DRUG":
                normalized = _clean_medication_phrase(entity.expanded_text or entity.text)
                if normalized:
                    return normalized

        therapy_match = re.search(
            r"\b(?:pd-1(?:/pd-l1)?(?:\s+inhibitor)?\s+therapy|pd-l1\s+therapy|"
            r"platinum-based chemotherapy|chemotherapy|kras-targeted therapy|agent targeting kras)\b",
            text,
            re.I,
        )
        if therapy_match:
            return _clean_medication_phrase(therapy_match.group(0))
        return None

    def _medication_exception_entities(self, text: str, entities: list[Entity], neg_result) -> list[str]:
        if not neg_result or not neg_result.exception_text:
            return []
        if _PHYSIOLOGIC_ALLOWANCE_PATTERN.search(neg_result.exception_text):
            return []

        exception_text = neg_result.exception_text
        values: list[str] = []
        exception_offset = text.casefold().find(exception_text.casefold())
        if exception_offset >= 0:
            exception_end = exception_offset + len(exception_text)
            for entity in entities:
                if entity.label != "DRUG":
                    continue
                if exception_offset <= entity.start < exception_end:
                    normalized = _clean_medication_exception_entity(entity.expanded_text or entity.text)
                    if normalized and normalized not in values:
                        values.append(normalized)

        if values:
            return values

        exception_body = _MEDICATION_EXCEPTION_TRUNCATION_PATTERN.split(exception_text, maxsplit=1)[0]
        exception_body = re.sub(r"^for\s+", "", exception_body.strip(), flags=re.I)
        raw_values = re.split(r"\s*,\s*|\s+\bor\b\s+|\s+\band/or\b\s+", exception_body)
        for raw_value in raw_values:
            normalized = _clean_medication_exception_entity(raw_value)
            if normalized and normalized not in values:
                values.append(normalized)
        return values

    def _medication_allowance_text(self, text: str, neg_result) -> str | None:
        source_text = f"{text} {neg_result.exception_text}" if neg_result and neg_result.exception_text else text
        match = _PHYSIOLOGIC_ALLOWANCE_PATTERN.search(source_text)
        if match:
            return _clean_medication_phrase(match.group(0))
        if neg_result and neg_result.exception_text:
            lowered = neg_result.exception_text.casefold()
            if any(token in lowered for token in ("allowed", "permitted", "replacement dose")):
                return neg_result.exception_text.strip()
        return None

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

    def _semantic_details(
        self,
        category: str,
        text: str,
        entities: list[Entity],
        *,
        neg_result=None,
        temporal=None,
    ) -> dict[str, object]:
        secondary_tags: list[str] = []
        specimen_types = _extract_specimen_types(text)
        testing_modalities = _extract_testing_modalities(text)
        assay_context: dict[str, object] | None = None
        exception_logic: dict[str, object] | None = None
        exception_entities: list[str] = []
        allowance_text: str | None = None

        if specimen_types:
            secondary_tags.append("specimen_context")
        if testing_modalities:
            secondary_tags.append("testing_modality")
        if (
            category in {"prior_therapy", "line_of_therapy", "concomitant_medication"}
            and _DISEASE_STATUS_PATTERN.search(text)
        ):
            secondary_tags.append("progression_requirement")
        if category in {"diagnosis", "cns_metastases"} and _STAGE_PATTERN.search(text):
            secondary_tags.append("stage_context")
        if category == "diagnosis" and _PRIOR_THERAPY_TEXT_PATTERN.search(text):
            secondary_tags.append("therapy_context")
        if category in {"diagnosis", "histology"} and _HISTOLOGY_PATTERN.search(text):
            secondary_tags.append("histology_context")

        if specimen_types or testing_modalities:
            assay_context = {
                "specimen_types": specimen_types,
                "testing_modalities": testing_modalities,
            }
        if category == "concomitant_medication":
            (
                exception_logic,
                exception_entities,
                allowance_text,
            ) = self._medication_semantics(
                text,
                entities,
                neg_result=neg_result,
                temporal=temporal,
            )
            if exception_logic:
                secondary_tags.append("medication_logic")
            if exception_entities:
                secondary_tags.append("medication_exception_entities")
            if allowance_text:
                secondary_tags.append("medication_allowance")

        return {
            "secondary_semantic_tags": secondary_tags,
            "specimen_type": specimen_types[0] if specimen_types else None,
            "testing_modality": testing_modalities[0] if testing_modalities else None,
            "disease_subtype": _extract_disease_subtype(text),
            "histology_text": _extract_histology_text(text),
            "assay_context": assay_context,
            "exception_logic": exception_logic,
            "exception_entities": exception_entities,
            "allowance_text": allowance_text,
        }

    def _score_confidence(
        self,
        *,
        category: str,
        parse_status: str,
        text: str,
        entities: list[Entity],
        quant: QuantitativeValue | None,
        temporal,
        semantic_details: dict[str, object],
        value_text: str | None,
        base_override: float | None = None,
    ) -> tuple[float, dict[str, object]]:
        if parse_status == "unparsed":
            return 0.0, {"parse_status": "unparsed"}

        if base_override is None:
            score = 0.42 if parse_status == "partial" else 0.52
        else:
            score = base_override

        structured_components: list[str] = []
        if entities:
            score += 0.12
            structured_components.append("entities")
        if quant:
            score += 0.08
            structured_components.append("quantitative")
        if temporal:
            score += 0.08
            structured_components.append("temporal")
        if semantic_details.get("specimen_type"):
            score += 0.05
            structured_components.append("specimen_type")
        if semantic_details.get("testing_modality"):
            score += 0.05
            structured_components.append("testing_modality")
        if semantic_details.get("assay_context"):
            score += 0.06
            structured_components.append("assay_context")
        if semantic_details.get("exception_logic"):
            score += 0.06
            structured_components.append("exception_logic")
        if semantic_details.get("exception_entities"):
            score += min(0.06, 0.02 * len(semantic_details["exception_entities"]))
            structured_components.append("exception_entities")
        if semantic_details.get("allowance_text"):
            score += 0.04
            structured_components.append("allowance_text")
        if semantic_details.get("disease_subtype"):
            score += 0.05
            structured_components.append("disease_subtype")
        if semantic_details.get("histology_text"):
            score += 0.05
            structured_components.append("histology_text")
        if semantic_details.get("secondary_semantic_tags"):
            score += min(0.08, 0.02 * len(semantic_details["secondary_semantic_tags"]))
            structured_components.append("secondary_semantics")
        if value_text:
            score += 0.07
            structured_components.append("semantic_value")
        if text and len(text) < 180:
            score += 0.03
        if _criterion_is_overloaded(text=text, category=category, entities=entities):
            overload_penalty = 0.18
            if category == "molecular_alteration" and semantic_details.get("assay_context"):
                overload_penalty = 0.06
            score -= overload_penalty
            structured_components.append("overloaded_penalty")

        if parse_status == "partial":
            score = min(score, 0.58)
        score = max(0.0, min(score, 0.92))
        return score, {
            "parse_status": parse_status,
            "structured_components": structured_components,
            "entity_count": len(entities),
            "secondary_semantic_tags": semantic_details.get("secondary_semantic_tags", []),
        }


def _extract_specimen_types(text: str) -> list[str]:
    values: list[str] = []
    for pattern, label in _SPECIMEN_PATTERNS:
        if pattern.search(text) and label not in values:
            values.append(label)
    return values


def _extract_testing_modalities(text: str) -> list[str]:
    values: list[str] = []
    for pattern, label in _TESTING_MODALITY_PATTERNS:
        if pattern.search(text) and label not in values:
            values.append(label)
    return values


def _extract_disease_subtype(text: str) -> str | None:
    if _NSCLC_SUBTYPE_PATTERN.search(text):
        return "non-small cell"
    if _SCLC_SUBTYPE_PATTERN.search(text):
        return "small cell"
    return None


def _extract_histology_text(text: str) -> str | None:
    matches = [match.group(0).lower() for match in _HISTOLOGY_VALUE_PATTERN.finditer(text)]
    if not matches:
        return None
    unique: list[str] = []
    for match in matches:
        if match not in unique:
            unique.append(match)
    return ", ".join(unique)


def _criterion_is_overloaded(*, text: str, category: str, entities: list[Entity]) -> bool:
    if category in {"diagnosis", "molecular_alteration"} and len(entities) >= 3:
        return True
    if category == "diagnosis" and _MOLECULAR_PATTERN.search(text):
        return True
    if category == "molecular_alteration" and _STAGE_PATTERN.search(text):
        return True
    return False


def _clean_medication_phrase(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"^[*()\s]+|[*()\s]+$", "", value)
    normalized = re.sub(r"^(?:and|or)\b\s*", "", normalized, flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,;.")
    return normalized.casefold() if normalized else None


def _clean_medication_exception_entity(value: str | None) -> str | None:
    normalized = _clean_medication_phrase(value)
    if not normalized:
        return None
    normalized = re.sub(r"^systemic\s+", "", normalized, flags=re.I)
    return normalized or None
