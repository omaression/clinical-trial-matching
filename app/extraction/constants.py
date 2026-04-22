"""Shared terminology constants used by extraction-adjacent modules."""

PD_1_THERAPY_SYNONYMS = (
    "pd-1 therapy",
    "pd 1 therapy",
    "pd-1 inhibitor therapy",
    "pd 1 inhibitor therapy",
    "programmed cell death protein 1 therapy",
    "programmed cell death protein 1 (pd-1) therapy",
)

PD_L1_THERAPY_SYNONYMS = (
    "pd-l1 therapy",
    "pd l1 therapy",
    "pd-l1 inhibitor therapy",
    "pd l1 inhibitor therapy",
    "programmed death-ligand 1 therapy",
    "programmed death ligand 1 therapy",
    "programmed death-ligand 1 (pd-l1) therapy",
    "programmed death ligand 1 (pd l1) therapy",
)

RECOGNIZED_MEDICATION_CLASS_TERMS = frozenset(
    {
        "pd-1 therapy",
        "pd-1/pd-l1 therapy",
        "pd-1/pd-l1 inhibitor therapy",
        "pd-l1 therapy",
        "kras-targeted therapy",
        "agent targeting kras",
        "systemic corticosteroids",
        "live-attenuated vaccine",
        "live vaccine",
        "live or live-attenuated vaccine",
        "cyp3a4 inhibitors/inducers",
        "platinum-based chemotherapy",
    }
)

AMBIGUOUS_MEDICATION_CLASS_HINTS = frozenset(
    {
        "therapy",
        "vaccine",
        "corticosteroid",
        "steroid",
        "chemotherapy",
        "inhibitor",
        "inducer",
        "immunosuppressive",
        "targeted",
        "targeting",
        "antibody",
        "agent",
    }
)
