from app.scripts.seed import LOINC_LABS, MESH_DISEASES, NCI_BIOMARKERS, NCI_DRUGS


def _synonyms_by_display(rows):
    return {display: set(synonyms) for _, display, synonyms in rows}


def test_seed_catalog_includes_common_disease_alias_variants():
    synonyms = _synonyms_by_display(MESH_DISEASES)

    assert "triple-negative breast cancer" in synonyms["Triple Negative Breast Neoplasms"]
    assert "non-small-cell lung cancer" in synonyms["Carcinoma, Non-Small-Cell Lung"]


def test_seed_catalog_includes_common_biomarker_alias_variants():
    synonyms = _synonyms_by_display(NCI_BIOMARKERS)

    assert "her2/neu positive" in synonyms["HER2 Positive"]
    assert "pd l1 positive" in synonyms["PD-L1 Positive"]
    assert "egfr mutated" in synonyms["EGFR Mutation Positive"]


def test_seed_catalog_includes_common_drug_and_lab_alias_variants():
    drug_synonyms = _synonyms_by_display(NCI_DRUGS)
    lab_synonyms = _synonyms_by_display(LOINC_LABS)

    assert "ado trastuzumab emtansine" in drug_synonyms["T-DM1"]
    assert "fam trastuzumab deruxtecan" in drug_synonyms["Trastuzumab Deruxtecan"]
    assert "5 fluorouracil" in drug_synonyms["Fluorouracil"]
    assert "absolute neutrophils" in lab_synonyms["Neutrophils [#/volume] in Blood"]
    assert "serum creatinine level" in lab_synonyms["Creatinine [Mass/volume] in Serum"]
