import uuid

from app.extraction.types import Entity
from app.fhir.criterion_projection import CriterionProjectionMapper


def _make_criterion(**kwargs):
    defaults = {
        "id": uuid.uuid4(),
        "trial_id": uuid.uuid4(),
        "type": "exclusion",
        "category": "concomitant_medication",
        "original_text": (
            "Systemic corticosteroids are excluded except for physiologic replacement doses "
            "of prednisone."
        ),
        "value_text": "systemic corticosteroids",
        "entities": [Entity(text="Systemic corticosteroids", label="DRUG", start=0, end=25)],
        "exception_entities": [],
        "allowance_text": "physiologic replacement doses of prednisone",
        "timeframe_operator": None,
        "timeframe_value": None,
        "timeframe_unit": None,
    }
    defaults.update(kwargs)

    class FakeCriterion:
        pass

    criterion = FakeCriterion()
    for key, value in defaults.items():
        setattr(criterion, key, value)
    return criterion


def test_named_drug_allowance_projects_to_medication_statement():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion()

    projections = mapper.project_criterion(criterion)

    statuses = {projection.normalized_term: projection.projection_status for projection in projections}
    assert statuses["systemic corticosteroids"] == "blocked_missing_class_code"
    assert statuses["prednisone"] == "projected"

    prednisone_projection = next(
        projection for projection in projections if projection.normalized_term == "prednisone"
    )
    assert prednisone_projection.resource_type == "MedicationStatement"
    assert prednisone_projection.terminology_status == "rxnorm_grounded"
    assert prednisone_projection.code == "8640"
    assert prednisone_projection.resource["medicationCodeableConcept"]["coding"][0]["system"] == (
        "http://www.nlm.nih.gov/research/umls/rxnorm"
    )


def test_safe_pd_1_therapy_class_projects_to_medication_statement():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        category="prior_therapy",
        type="inclusion",
        original_text="Prior PD-1 therapy for metastatic disease",
        value_text="pd-1 therapy",
        entities=[Entity(text="PD-1 therapy", label="DRUG", start=6, end=18)],
        allowance_text=None,
    )

    projections = mapper.project_criterion(criterion)

    assert len(projections) == 1
    assert projections[0].projection_status == "projected"
    assert projections[0].terminology_status == "nci_thesaurus_grounded"
    assert projections[0].review_required is False
    assert projections[0].code == "C178320"
    assert projections[0].resource_type == "MedicationStatement"
    assert projections[0].resource["medicationCodeableConcept"]["coding"][0]["system"] == (
        "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
    )


def test_named_drug_wrapper_projects_via_embedded_rxnorm_drug():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        category="prior_therapy",
        type="inclusion",
        original_text="Have documented disease progression after receiving at least 1 trastuzumab-containing treatment",
        value_text="trastuzumab-containing treatment",
        entities=[Entity(text="trastuzumab", label="DRUG", start=58, end=69)],
        allowance_text=None,
    )

    projections = mapper.project_criterion(criterion)

    projected = [projection for projection in projections if projection.projection_status == "projected"]
    assert len(projected) == 1
    assert projected[0].code == "224905"
    assert projected[0].terminology_status == "rxnorm_grounded"
    assert projected[0].resource_type == "MedicationStatement"
    assert projected[0].resource["medicationCodeableConcept"]["coding"][0]["system"] == (
        "http://www.nlm.nih.gov/research/umls/rxnorm"
    )
    assert projected[0].resource["medicationCodeableConcept"]["coding"][0]["code"] == "224905"


def test_explicit_combination_splits_into_named_drug_and_safe_parent_class_projections():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        category="prior_therapy",
        type="inclusion",
        original_text="Prior trastuzumab + chemotherapy",
        value_text="trastuzumab + chemotherapy",
        entities=[Entity(text="trastuzumab", label="DRUG", start=6, end=17)],
        allowance_text=None,
    )

    projections = mapper.project_criterion(criterion)

    assert len(projections) == 2
    codes = {projection.code for projection in projections if projection.projection_status == "projected"}
    assert codes == {"224905", "C15632"}

    trastuzumab = next(projection for projection in projections if projection.code == "224905")
    chemotherapy = next(projection for projection in projections if projection.code == "C15632")
    assert trastuzumab.resource["medicationCodeableConcept"]["text"] == "trastuzumab"
    assert chemotherapy.resource["medicationCodeableConcept"]["text"] == "chemotherapy"
    assert chemotherapy.terminology_status == "nci_thesaurus_grounded"


def test_investigational_agent_projects_to_safe_parent_class_with_verbatim_text():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        category="prior_therapy",
        type="inclusion",
        original_text="Prior investigational agent",
        value_text="investigational agent",
        entities=[],
        allowance_text=None,
    )

    projections = mapper.project_criterion(criterion)

    assert len(projections) == 1
    assert projections[0].projection_status == "projected"
    assert projections[0].terminology_status == "nci_thesaurus_grounded"
    assert projections[0].code == "C202579"
    assert projections[0].resource["medicationCodeableConcept"]["text"] == "investigational agent"
