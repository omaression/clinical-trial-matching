from collections import Counter

from app.scripts.seed import (
    LOINC_LABS,
    MESH_DISEASES,
    NCI_BIOMARKERS,
    NCI_DRUGS,
    NCI_SCALES,
    SNOMED_PROCEDURES,
    _merge_synonyms,
)


def _synonyms_by_display(rows):
    return {display: set(synonyms) for _, display, synonyms in rows}


def _catalog_rows():
    for system, rows in (
        ("mesh", MESH_DISEASES),
        ("nci_thesaurus", NCI_BIOMARKERS + NCI_DRUGS + NCI_SCALES),
        ("snomed_ct", SNOMED_PROCEDURES),
        ("loinc", LOINC_LABS),
    ):
        for code, display, _synonyms in rows:
            yield system, code, display


def test_seed_catalog_includes_common_disease_alias_variants():
    synonyms = _synonyms_by_display(MESH_DISEASES)

    assert "triple-negative breast cancer" in synonyms["Triple Negative Breast Neoplasms"]
    assert "non-small-cell lung cancer" in synonyms["Carcinoma, Non-Small-Cell Lung"]
    assert "hiv infection" in synonyms["HIV Infections"]
    assert "interstitial lung disease" in synonyms["Lung Diseases, Interstitial"]
    assert "active cns metastases" in synonyms["Brain Neoplasms"]
    assert "active inflammatory bowel disease" in synonyms["Inflammatory Bowel Diseases"]
    assert "cardiovascular disorder" in synonyms["Cardiovascular Diseases"]
    assert "cerebrovascular disease" in synonyms["Cerebrovascular Disorders"]
    assert "active infection" in synonyms["Infections"]
    assert "clinically severe pulmonary compromise" in synonyms["Respiratory Insufficiency"]
    assert "uncontrolled diabetes" in synonyms["Diabetes Mellitus"]
    assert "connective tissue diseases" in synonyms["Connective Tissue Diseases"]
    assert "soft tissue sarcoma" in synonyms["Sarcoma"]
    assert "invasive ductal breast carcinoma" in synonyms["Breast Neoplasms"]
    assert "primary cns tumors" in synonyms["Brain Neoplasms"]
    assert "meibomian gland dysfunction" in synonyms["Blepharitis"]
    assert "kaposi's sarcoma" in synonyms["Sarcoma, Kaposi"]
    assert "multicentric castleman disease" in synonyms["Castleman Disease"]


def test_seed_catalog_includes_common_biomarker_alias_variants():
    synonyms = _synonyms_by_display(NCI_BIOMARKERS)

    assert "her2/neu positive" in synonyms["HER2 Positive"]
    assert "pd l1 positive" in synonyms["PD-L1 Positive"]
    assert "egfr mutated" in synonyms["EGFR Mutation Positive"]
    assert "kras g12c mutation" in synonyms["KRAS Mutation Positive"]


def test_seed_catalog_includes_common_drug_and_lab_alias_variants():
    drug_synonyms = _synonyms_by_display(NCI_DRUGS)
    lab_synonyms = _synonyms_by_display(LOINC_LABS)

    assert "ado trastuzumab emtansine" in drug_synonyms["T-DM1"]
    assert "fam trastuzumab deruxtecan" in drug_synonyms["Trastuzumab Deruxtecan"]
    assert "5 fluorouracil" in drug_synonyms["Fluorouracil"]
    assert "pd-l1 therapy" in drug_synonyms["anti-PD-L1 monoclonal antibody"]
    assert "absolute neutrophils" in lab_synonyms["Neutrophils [#/volume] in Blood"]
    assert "serum creatinine level" in lab_synonyms["Creatinine [Mass/volume] in Serum"]


def test_seed_catalog_includes_common_procedural_alias_variants():
    synonyms = _synonyms_by_display(SNOMED_PROCEDURES)

    assert "archival tumor tissue sample" in synonyms["Specimen collection"]
    assert "newly obtained biopsy" in synonyms["Biopsy"]
    assert "major surgery" in synonyms["Surgical procedure"]


def test_seed_catalog_uses_unique_codes_within_each_system():
    counts = Counter((system, code) for system, code, _display in _catalog_rows())
    duplicates = [key for key, count in counts.items() if count > 1]

    assert duplicates == []


def test_seed_catalog_keeps_expected_nci_drug_codes():
    codes = {display: code for code, display, _synonyms in NCI_DRUGS}

    assert codes["Carboplatin"] == "C1282"
    assert codes["Docetaxel"] == "C1526"
    assert codes["Capecitabine"] == "C1794"


def test_merge_synonyms_is_case_insensitive_and_append_only():
    merged = _merge_synonyms(
        ["KRAS mutant", "hiv infection"],
        ["kras mutant", "KRAS G12C mutation", "HIV Infection", "  well-controlled HIV  "],
    )

    assert merged == [
        "KRAS mutant",
        "hiv infection",
        "KRAS G12C mutation",
        "well-controlled HIV",
    ]
