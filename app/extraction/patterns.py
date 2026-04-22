"""Common regex patterns for the extraction pipeline."""

import re

# Long-form drug patterns (e.g., PD-L1 full spelling variations)
LONG_FORM_DRUG_PATTERNS = (
    re.compile(
        r"programmed\s+death(?:-|\s+)ligand\s+1\s*\(\s*PD(?:-|\s*)L1\s*\)\s*therapy",
        re.I,
    ),
)

# Progression criteria - "progression after receiving..."
PROGRESSION_AFTER_RECEIVING_PATTERN = re.compile(
    r"^(?P<prefix>.*?\b(?:documented\s+disease\s+progression|disease\s+progression|progression)\b.*?\bafter\b\s+\b(?:receiving|receipt\s+of)\b)\s+(?P<tail>.+)$",
    re.I,
)

# Progression with "including" construction
INCLUDING_PROGRESSION_PATTERN = re.compile(
    r"^(?P<lemma>\*?\s*(?:has|have))\s+(?P<head>.+?),\s+including\s+(?P<tail>disease\s+progression\s+after\s+receiving.+)$",
    re.I | re.S,
)

# "of the following types" enumeration patterns
FOLLOWING_TYPES_PATTERN = re.compile(
    r"^(?P<prefix>.*?)(?P<intro>\b(?:of\s+the\s+following\s+types|following\s+types|following\s+histologies)\s*:)\s*"
    r"(?P<items>.+?)(?P<tail>,?\s*(?:who|that)\b.+)$",
    re.I | re.S,
)

# Diagnosis or medication split pattern
DIAGNOSIS_MEDICATION_SPLIT_PATTERN = re.compile(
    r"^(?P<bullet>\*?\s*)(?P<lemma>has|have)\s+(?:a\s+diagnosis\s+of|diagnosis\s+of)\s+"
    r"(?P<diagnosis>.+?)\s+or\s+(?P<medication>(?:is\s+receiving|receiving|using|use\s+of).+)$",
    re.I,
)

# Medication verb pattern (is receiving, receiving, etc.)
MEDICATION_LEMMA_PATTERN = re.compile(
    r"^(?P<verb>is\s+receiving|receiving|using|use\s+of)\s+(?P<body>.+)$",
    re.I,
)

# Temporal tail indicators (within, at least, prior to, etc.)
TEMPORAL_TAIL_PATTERN = re.compile(
    r"\b(?:within|at\s+least|no\s+more\s+than|prior\s+to|since|more\s+than|>)\b.+$",
    re.I,
)

# Medication signals (vaccine, corticosteroid, immunosuppressive, etc.)
MEDICATION_SIGNAL_PATTERN = re.compile(
    r"\b(?:vaccine|corticosteroid|steroid\s+therapy|immunosuppressive\s+therapy|"
    r"immunosuppressive\s+medications?|immunosuppressants?|cyp[0-9a-z-]+)\b",
    re.I,
)

# Enumeration connectors (comma, or, and/or)
ENUMERATION_CONNECTOR_PATTERN = re.compile(r"\s*(?:,\s*|\bor\b\s*|\band/or\b\s*)", re.I)
