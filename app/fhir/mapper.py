from app.models.database import ExtractedCriterion, Trial

# FHIR status mapping from ClinicalTrials.gov
_STATUS_MAP = {
    "RECRUITING": "active",
    "ACTIVE_NOT_RECRUITING": "active",
    "NOT_YET_RECRUITING": "approved",
    "COMPLETED": "completed",
    "TERMINATED": "closed-to-accrual",
    "SUSPENDED": "temporarily-closed-to-accrual",
    "WITHDRAWN": "withdrawn",
    "ENROLLING_BY_INVITATION": "active",
}

_PHASE_MAP = {
    "PHASE1": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/research-study-phase",
                "code": "phase-1",
                "display": "Phase 1",
            }
        ]
    },
    "PHASE2": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/research-study-phase",
                "code": "phase-2",
                "display": "Phase 2",
            }
        ]
    },
    "PHASE3": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/research-study-phase",
                "code": "phase-3",
                "display": "Phase 3",
            }
        ]
    },
    "PHASE4": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/research-study-phase",
                "code": "phase-4",
                "display": "Phase 4",
            }
        ]
    },
    "EARLY_PHASE1": {
        "coding": [
            {
                "system": "http://terminology.hl7.org/CodeSystem/research-study-phase",
                "code": "early-phase-1",
                "display": "Early Phase 1",
            }
        ]
    },
}

_ELIGIBILITY_EXT_URL = "http://hl7.org/fhir/StructureDefinition/researchStudy-eligibility"
_INTERNAL_ONLY_ELIGIBILITY_CATEGORIES = {
    "administrative_requirement",
    "behavioral_constraint",
    "reproductive_status",
    "device_constraint",
    "procedural_requirement",
    "disease_status",
}


class FHIRMapper:
    """Stage 5: Map Trial + extracted criteria to FHIR R4 ResearchStudy."""

    def to_research_study(self, trial: Trial, criteria: list[ExtractedCriterion]) -> dict:
        resource = {
            "resourceType": "ResearchStudy",
            "identifier": [
                {
                    "system": "https://clinicaltrials.gov",
                    "value": trial.nct_id,
                }
            ],
            "title": trial.brief_title,
            "status": _STATUS_MAP.get(trial.status, "active"),
        }

        # Phase
        if trial.phase:
            phase_key = trial.phase.split(",")[0].strip()
            if phase_key in _PHASE_MAP:
                resource["phase"] = _PHASE_MAP[phase_key]

        # Conditions
        if trial.conditions:
            resource["condition"] = [
                {"text": c} for c in trial.conditions
            ]

        # Eligibility criteria as extensions
        exportable = self._filter_exportable(criteria)
        inclusion = [c for c in exportable if c.type == "inclusion"]
        exclusion = [c for c in exportable if c.type == "exclusion"]

        extensions = []
        if inclusion:
            inc_ext = {
                "url": f"{_ELIGIBILITY_EXT_URL}/inclusion",
                "extension": [self._criterion_to_extension(c) for c in inclusion],
            }
            extensions.append(inc_ext)
        if exclusion:
            exc_ext = {
                "url": f"{_ELIGIBILITY_EXT_URL}/exclusion",
                "extension": [self._criterion_to_extension(c) for c in exclusion],
            }
            extensions.append(exc_ext)

        if extensions:
            resource["extension"] = extensions

        # Enrollment age/sex
        if trial.eligible_min_age or trial.eligible_max_age or trial.eligible_sex:
            enrollment = {}
            if trial.eligible_min_age:
                enrollment["minimumAge"] = trial.eligible_min_age
            if trial.eligible_max_age:
                enrollment["maximumAge"] = trial.eligible_max_age
            if trial.eligible_sex:
                enrollment["sex"] = trial.eligible_sex
            resource["enrollment"] = [enrollment]

        return resource

    def _filter_exportable(self, criteria: list[ExtractedCriterion]) -> list[ExtractedCriterion]:
        """Only export criteria that are structurally usable and no longer pending review."""
        exportable = []
        for c in criteria:
            if c.parse_status not in ("parsed", "partial"):
                continue
            if c.category == "other":
                continue
            if c.category in _INTERNAL_ONLY_ELIGIBILITY_CATEGORIES:
                continue
            if c.category == "concomitant_medication" and (
                getattr(c, "exception_logic", None)
                or getattr(c, "allowance_text", None)
            ):
                continue
            review_status = getattr(c, "review_status", None)
            if review_status == "rejected":
                continue
            if c.review_required and review_status not in {"accepted", "corrected"}:
                continue
            if not self._has_semantic_payload(c):
                continue
            exportable.append(c)
        return exportable

    def _has_semantic_payload(self, criterion: ExtractedCriterion) -> bool:
        if criterion.coded_concepts:
            return True
        if criterion.operator or criterion.value_low is not None or criterion.value_high is not None or criterion.unit:
            return True
        if getattr(criterion, "value_text", None):
            return True
        if (
            getattr(criterion, "timeframe_operator", None)
            or getattr(criterion, "timeframe_value", None) is not None
            or getattr(criterion, "timeframe_unit", None)
        ):
            return True
        if getattr(criterion, "specimen_type", None) or getattr(criterion, "testing_modality", None):
            return True
        if getattr(criterion, "assay_context", None):
            return True
        if getattr(criterion, "disease_subtype", None) or getattr(criterion, "histology_text", None):
            return True
        return False

    def _criterion_to_extension(self, criterion: ExtractedCriterion) -> dict:
        ext = {
            "url": "criterion",
            "extension": [
                {"url": "category", "valueString": criterion.category},
                {
                    "url": "primarySemanticCategory",
                    "valueString": getattr(criterion, "primary_semantic_category", None) or criterion.category,
                },
                {"url": "text", "valueString": criterion.original_text},
            ],
        }
        source_sentence = getattr(criterion, "source_sentence", None)
        if source_sentence:
            ext["extension"].append({"url": "sourceSentence", "valueString": source_sentence})
        source_clause_text = getattr(criterion, "source_clause_text", None)
        if source_clause_text and source_clause_text != criterion.original_text:
            ext["extension"].append({"url": "sourceClauseText", "valueString": source_clause_text})
        if criterion.operator:
            ext["extension"].append({"url": "operator", "valueString": criterion.operator})
        if criterion.value_low is not None:
            ext["extension"].append({"url": "valueLow", "valueDecimal": criterion.value_low})
        if criterion.value_high is not None:
            ext["extension"].append({"url": "valueHigh", "valueDecimal": criterion.value_high})
        if getattr(criterion, "value_text", None):
            ext["extension"].append({"url": "valueText", "valueString": criterion.value_text})
        if criterion.unit:
            ext["extension"].append({"url": "unit", "valueString": criterion.unit})
        if criterion.negated:
            ext["extension"].append({"url": "negated", "valueBoolean": True})
        if getattr(criterion, "timeframe_operator", None):
            ext["extension"].append({"url": "timeframeOperator", "valueString": criterion.timeframe_operator})
        if getattr(criterion, "timeframe_value", None) is not None:
            ext["extension"].append({"url": "timeframeValue", "valueDecimal": criterion.timeframe_value})
        if getattr(criterion, "timeframe_unit", None):
            ext["extension"].append({"url": "timeframeUnit", "valueString": criterion.timeframe_unit})
        if getattr(criterion, "specimen_type", None):
            ext["extension"].append({"url": "specimenType", "valueString": criterion.specimen_type})
        if getattr(criterion, "testing_modality", None):
            ext["extension"].append({"url": "testingModality", "valueString": criterion.testing_modality})
        if getattr(criterion, "disease_subtype", None):
            ext["extension"].append({"url": "diseaseSubtype", "valueString": criterion.disease_subtype})
        if getattr(criterion, "histology_text", None):
            ext["extension"].append({"url": "histologyText", "valueString": criterion.histology_text})
        assay_context = getattr(criterion, "assay_context", None)
        if isinstance(assay_context, dict):
            for specimen_type in assay_context.get("specimen_types", []) or []:
                ext["extension"].append({"url": "assaySpecimenType", "valueString": specimen_type})
            for testing_modality in assay_context.get("testing_modalities", []) or []:
                ext["extension"].append({"url": "assayTestingModality", "valueString": testing_modality})
        for tag in getattr(criterion, "secondary_semantic_tags", []) or []:
            ext["extension"].append({"url": "secondarySemanticTag", "valueString": tag})
        if criterion.coded_concepts:
            for concept in (criterion.coded_concepts if isinstance(criterion.coded_concepts, list) else []):
                if isinstance(concept, dict):
                    ext["extension"].append({
                        "url": "coding",
                        "valueCoding": {
                            "system": concept.get("system", ""),
                            "code": concept.get("code", ""),
                            "display": concept.get("display", ""),
                        },
                    })
        if criterion.logic_group_id:
            ext["extension"].append({
                "url": "logicGroupId",
                "valueString": str(criterion.logic_group_id),
            })
            ext["extension"].append({
                "url": "logicOperator",
                "valueString": criterion.logic_operator,
            })
        return ext
