import uuid

import pytest

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


def test_systemic_corticosteroid_class_and_named_allowance_project_to_medication_statements():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion()

    projections = mapper.project_criterion(criterion)

    statuses = {projection.normalized_term: projection.projection_status for projection in projections}
    assert statuses["systemic corticosteroids"] == "projected"
    assert statuses["prednisone"] == "projected"

    systemic_projection = next(
        projection for projection in projections if projection.normalized_term == "systemic corticosteroids"
    )
    assert systemic_projection.resource_type == "MedicationStatement"
    assert systemic_projection.terminology_status == "nci_thesaurus_grounded"
    assert systemic_projection.code == "C122080"
    assert systemic_projection.resource["medicationCodeableConcept"]["coding"][0]["system"] == (
        "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
    )

    prednisone_projection = next(
        projection for projection in projections if projection.normalized_term == "prednisone"
    )
    assert prednisone_projection.resource_type == "MedicationStatement"
    assert prednisone_projection.terminology_status == "rxnorm_grounded"
    assert prednisone_projection.code == "8640"
    assert prednisone_projection.resource["medicationCodeableConcept"]["coding"][0]["system"] == (
        "http://www.nlm.nih.gov/research/umls/rxnorm"
    )


@pytest.mark.parametrize(
    "mention_text",
    [
        "live vaccine",
        "live-attenuated vaccine",
        "live or live-attenuated vaccine",
    ],
)
def test_live_vaccine_variants_project_to_safe_parent_class(mention_text: str):
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        original_text=f"No {mention_text} within 30 days before enrollment",
        value_text=mention_text,
        entities=[Entity(text=mention_text, label="DRUG", start=3, end=3 + len(mention_text))],
        allowance_text=None,
        timeframe_operator="within",
        timeframe_value=30.0,
        timeframe_unit="days",
    )

    projections = mapper.project_criterion(criterion)

    assert len(projections) == 1
    assert projections[0].mention_text == mention_text
    assert projections[0].projection_status == "projected"
    assert projections[0].terminology_status == "nci_thesaurus_grounded"
    assert projections[0].review_required is False
    assert projections[0].code == "C97116"
    assert projections[0].resource_type == "MedicationStatement"
    assert projections[0].resource["medicationCodeableConcept"]["coding"][0]["system"] == (
        "http://ncicb.nci.nih.gov/xml/owl/EVS/Thesaurus.owl"
    )


def test_generic_vaccine_term_remains_review_required_for_safety():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        original_text="No vaccine within 30 days before enrollment",
        value_text="vaccine",
        entities=[Entity(text="vaccine", label="DRUG", start=3, end=10)],
        allowance_text=None,
        timeframe_operator="within",
        timeframe_value=30.0,
        timeframe_unit="days",
    )

    projections = mapper.project_criterion(criterion)

    assert len(projections) == 1
    assert projections[0].normalized_term == "vaccine"
    assert projections[0].projection_status == "review_required_ambiguous_class"
    assert projections[0].terminology_status == "ambiguous_class_no_safe_code"
    assert projections[0].review_required is True
    assert projections[0].resource is None


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


def test_cyp3a4_inducer_inhibitor_class_remains_blocked_pending_safe_source():
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        original_text="No concurrent CYP3A4 inhibitors/inducers within 7 days",
        value_text="cyp3a4 inhibitors/inducers",
        entities=[Entity(text="CYP3A4 inhibitors/inducers", label="DRUG", start=14, end=40)],
        allowance_text=None,
        exception_entities=[],
        timeframe_operator="within",
        timeframe_value=7.0,
        timeframe_unit="days",
    )

    projections = mapper.project_criterion(criterion)

    assert len(projections) == 1
    assert projections[0].normalized_term == "cyp3a4 inhibitors inducers"
    assert projections[0].projection_status == "blocked_missing_class_code"
    assert projections[0].terminology_status == "recognized_class_missing_safe_code"
    assert projections[0].review_required is True
    assert projections[0].resource is None


@pytest.mark.parametrize(
    ("mention_text", "normalized_term"),
    [
        ("agent targeting kras", "agent targeting kras"),
        ("kras-targeted therapy", "kras targeted therapy"),
    ],
)
def test_kras_targeted_class_terms_remain_blocked_pending_safe_source(mention_text: str, normalized_term: str):
    mapper = CriterionProjectionMapper()
    criterion = _make_criterion(
        original_text=f"Has received previous treatment with {mention_text}",
        value_text=mention_text,
        entities=[Entity(text=mention_text, label="DRUG", start=36, end=36 + len(mention_text))],
        allowance_text=None,
    )

    projections = mapper.project_criterion(criterion)

    assert len(projections) == 1
    assert projections[0].normalized_term == normalized_term
    assert projections[0].projection_status == "blocked_missing_class_code"
    assert projections[0].terminology_status == "recognized_class_missing_safe_code"
    assert projections[0].review_required is True
    assert projections[0].resource is None
