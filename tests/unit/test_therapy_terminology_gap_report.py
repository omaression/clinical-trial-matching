from app.scripts.therapy_terminology_gap_report import build_therapy_terminology_gap_report


def test_therapy_terminology_gap_report_is_deterministic_for_default_fixtures():
    report = build_therapy_terminology_gap_report()

    assert report["metadata"]["fixture_names"] == [
        "concomitant_cns",
        "medication_exception_logic",
        "mixed_polarity",
        "nct03872596_cyp3a4_washout",
        "nct07084584_cyp3a4_exception",
        "therapy_class_and_procedures",
    ]
    assert report["summary"] == {
        "fixture_count": 6,
        "gap_count": 3,
        "occurrence_count": 6,
        "breakdown_by_status": {
            "blocked_missing_class_code": 5,
            "review_required_ambiguous_class": 1,
        },
        "breakdown_by_category": {
            "concomitant_medication": 4,
            "prior_therapy": 2,
        },
    }
    assert report["gaps"] == [
        {
            "projection_status": "blocked_missing_class_code",
            "terminology_status": "recognized_class_missing_safe_code",
            "normalized_term": "agent targeting kras",
            "occurrence_count": 1,
            "fixture_count": 1,
            "fixtures": ["therapy_class_and_procedures"],
            "criterion_categories": {"prior_therapy": 1},
            "criterion_types": {"exclusion": 1},
            "representative_examples": [
                {
                    "fixture": "therapy_class_and_procedures",
                    "criterion_type": "exclusion",
                    "criterion_category": "prior_therapy",
                    "mention_text": "agent targeting KRAS",
                    "criterion_text": "* Has received previous treatment with an agent targeting KRAS",
                }
            ],
        },
        {
            "projection_status": "blocked_missing_class_code",
            "terminology_status": "recognized_class_missing_safe_code",
            "normalized_term": "cyp3a4 inhibitors inducers",
            "occurrence_count": 4,
            "fixture_count": 4,
            "fixtures": [
                "concomitant_cns",
                "medication_exception_logic",
                "nct03872596_cyp3a4_washout",
                "nct07084584_cyp3a4_exception",
            ],
            "criterion_categories": {"concomitant_medication": 4},
            "criterion_types": {"exclusion": 4},
            "representative_examples": [
                {
                    "fixture": "concomitant_cns",
                    "criterion_type": "exclusion",
                    "criterion_category": "concomitant_medication",
                    "mention_text": "cyp3a4 inhibitors/inducers",
                    "criterion_text": "No concurrent CYP3A4 inhibitors",
                },
                {
                    "fixture": "medication_exception_logic",
                    "criterion_type": "exclusion",
                    "criterion_category": "concomitant_medication",
                    "mention_text": "cyp3a4 inhibitors/inducers",
                    "criterion_text": (
                        "Concurrent use of weak, moderate and strong CYP3A4 inhibitors/inducers "
                        "(except for systemic itraconazole, ketoconazole, posaconazole, or "
                        "voriconazole, which should have been started at least 7 days prior to "
                        "enrolment)."
                    ),
                },
                {
                    "fixture": "nct03872596_cyp3a4_washout",
                    "criterion_type": "exclusion",
                    "criterion_category": "concomitant_medication",
                    "mention_text": "cyp3a4 inhibitors/inducers",
                    "criterion_text": (
                        "Use of any moderate-strong CYP3A4 inhibitor or inducer within 14 days or "
                        "5 plasma half-lives (whichever is longer) prior to the administration of "
                        "IMP and for the duration of the trial."
                    ),
                },
            ],
        },
        {
            "projection_status": "review_required_ambiguous_class",
            "terminology_status": "ambiguous_class_no_safe_code",
            "normalized_term": "immunotherapy",
            "occurrence_count": 1,
            "fixture_count": 1,
            "fixtures": ["mixed_polarity"],
            "criterion_categories": {"prior_therapy": 1},
            "criterion_types": {"exclusion": 1},
            "representative_examples": [
                {
                    "fixture": "mixed_polarity",
                    "criterion_type": "exclusion",
                    "criterion_category": "prior_therapy",
                    "mention_text": "immunotherapy",
                    "criterion_text": "Patients must NOT have received prior immunotherapy",
                }
            ],
        },
    ]
