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


def test_recognized_therapy_class_without_safe_code_is_blocked_for_review():
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
    assert projections[0].projection_status == "blocked_missing_class_code"
    assert projections[0].terminology_status == "recognized_class_missing_safe_code"
    assert projections[0].review_required is True
    assert projections[0].resource is None
