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
    "PHASE1": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/research-study-phase", "code": "phase-1", "display": "Phase 1"}]},
    "PHASE2": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/research-study-phase", "code": "phase-2", "display": "Phase 2"}]},
    "PHASE3": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/research-study-phase", "code": "phase-3", "display": "Phase 3"}]},
    "PHASE4": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/research-study-phase", "code": "phase-4", "display": "Phase 4"}]},
    "EARLY_PHASE1": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/research-study-phase", "code": "early-phase-1", "display": "Early Phase 1"}]},
}

_ELIGIBILITY_EXT_URL = "http://hl7.org/fhir/StructureDefinition/researchStudy-eligibility"


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
        """Only export parsed/partial criteria that haven't been rejected."""
        exportable = []
        for c in criteria:
            if c.parse_status not in ("parsed", "partial"):
                continue
            if c.review_status == "rejected":
                continue
            exportable.append(c)
        return exportable

    def _criterion_to_extension(self, criterion: ExtractedCriterion) -> dict:
        ext = {
            "url": "criterion",
            "extension": [
                {"url": "category", "valueString": criterion.category},
                {"url": "text", "valueString": criterion.original_text},
            ],
        }
        if criterion.operator:
            ext["extension"].append({"url": "operator", "valueString": criterion.operator})
        if criterion.value_low is not None:
            ext["extension"].append({"url": "valueLow", "valueDecimal": criterion.value_low})
        if criterion.value_high is not None:
            ext["extension"].append({"url": "valueHigh", "valueDecimal": criterion.value_high})
        if criterion.unit:
            ext["extension"].append({"url": "unit", "valueString": criterion.unit})
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
        return ext
