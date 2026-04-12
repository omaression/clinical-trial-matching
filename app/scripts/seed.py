"""Seed the database with coding lookups for entity resolution."""

from app.db.session import SessionLocal
from app.models.database import CodingLookup

# MeSH disease codes
MESH_DISEASES = [
    ("D001943", "Breast Neoplasms", ["breast cancer", "breast carcinoma", "mammary cancer", "breast neoplasm"]),
    (
        "D000073182",
        "Triple Negative Breast Neoplasms",
        ["tnbc", "triple negative breast cancer", "triple-negative breast cancer"],
    ),
    (
        "D002289",
        "Carcinoma, Non-Small-Cell Lung",
        ["nsclc", "non-small cell lung cancer", "non-small cell lung carcinoma", "non-small-cell lung cancer"],
    ),
    ("D055752", "Small Cell Lung Carcinoma", ["sclc", "small cell lung cancer"]),
    ("D008545", "Melanoma", ["malignant melanoma"]),
    ("D006528", "Hepatocellular Carcinoma", ["hcc", "liver cancer", "hepatoma"]),
    ("D002277", "Carcinoma, Renal Cell", ["rcc", "renal cell carcinoma", "kidney cancer"]),
    ("D015179", "Colorectal Neoplasms", ["crc", "colorectal cancer", "colon cancer", "rectal cancer"]),
    ("D005909", "Glioblastoma", ["gbm", "glioblastoma multiforme"]),
    ("D015266", "Gastrointestinal Stromal Tumors", ["gist", "gastrointestinal stromal tumor"]),
    ("D015470", "Leukemia, Myeloid, Acute", ["aml", "acute myeloid leukemia"]),
    ("D015451", "Leukemia, Lymphocytic, Chronic, B-Cell", ["cll", "chronic lymphocytic leukemia"]),
    ("D016403", "Lymphoma, Large B-Cell, Diffuse", ["dlbcl", "diffuse large b-cell lymphoma"]),
    ("D000077195", "Squamous Cell Carcinoma of Head and Neck", ["hnscc", "head and neck squamous cell carcinoma"]),
    ("D010190", "Pancreatic Neoplasms", ["pancreatic cancer", "pancreatic carcinoma"]),
    ("D010051", "Ovarian Neoplasms", ["ovarian cancer", "ovarian carcinoma"]),
    ("D011471", "Prostatic Neoplasms", ["prostate cancer", "prostatic carcinoma"]),
    ("D064129", "Prostatic Neoplasms, Castration-Resistant", ["mcrpc", "castration-resistant prostate cancer", "crpc"]),
    (
        "D001859",
        "Brain Neoplasms",
        [
            "brain cancer",
            "brain tumor",
            "brain metastases",
            "brain metastasis",
            "cns metastases",
            "cns metastasis",
            "central nervous system metastases",
            "central nervous system metastasis",
            "active cns metastases",
            "active central nervous system metastases",
        ],
    ),
    ("D055756", "Leptomeningeal Carcinomatosis", ["leptomeningeal disease", "leptomeningeal metastases"]),
    (
        "D015658",
        "HIV Infections",
        [
            "hiv",
            "hiv infection",
            "hiv infections",
            "human immunodeficiency virus",
            "human immunodeficiency virus infection",
            "well-controlled hiv",
        ],
    ),
    (
        "D007153",
        "Immunologic Deficiency Syndromes",
        ["immunodeficiency", "immunologic deficiency", "immunological deficiency", "immune deficiency"],
    ),
    (
        "D017563",
        "Lung Diseases, Interstitial",
        ["interstitial lung disease", "interstitial lung diseases", "ild", "pneumonitis interstitial"],
    ),
    (
        "D012131",
        "Respiratory Insufficiency",
        ["pulmonary compromise", "severe pulmonary compromise", "clinically severe pulmonary compromise"],
    ),
    ("D007239", "Infections", ["infection", "active infection"]),
    (
        "D015212",
        "Inflammatory Bowel Diseases",
        ["inflammatory bowel disease", "active inflammatory bowel disease"],
    ),
    (
        "D002318",
        "Cardiovascular Diseases",
        ["cardiovascular disorder", "cardiovascular disease", "significant cardiovascular disorder"],
    ),
    (
        "D002561",
        "Cerebrovascular Disorders",
        ["cerebrovascular disease", "cerebrovascular disorder"],
    ),
    ("D003316", "Corneal Diseases", ["corneal disease", "corneal diseases"]),
    ("D015352", "Dry Eye Syndromes", ["dry eye syndrome", "dry eye", "dry eyes"]),
    (
        "D001762",
        "Blepharitis",
        ["blepharitis", "meibomitis", "meibomian gland disease", "meibomian gland dysfunction"],
    ),
    ("D012514", "Sarcoma, Kaposi", ["kaposi sarcoma", "kaposi's sarcoma"]),
    (
        "D005871",
        "Castleman Disease",
        [
            "castleman disease",
            "castleman's disease",
            "multicentric castleman disease",
            "multicentric castleman's disease",
        ],
    ),
    ("D013274", "Stomach Neoplasms", ["gastric cancer", "stomach cancer"]),
    ("D014571", "Urinary Bladder Neoplasms", ["bladder cancer", "urothelial carcinoma"]),
    ("D002051", "Burkitt Lymphoma", ["burkitt lymphoma"]),
    ("D008228", "Lymphoma, Non-Hodgkin", ["non-hodgkin lymphoma", "nhl"]),
    ("D006689", "Hodgkin Disease", ["hodgkin lymphoma", "hodgkin disease"]),
]

# NCI Thesaurus biomarker/molecular codes
NCI_BIOMARKERS = [
    ("C68748", "HER2 Positive", ["her2+", "erbb2 positive", "her2 positive", "her2/neu positive"]),
    ("C68749", "HER2 Negative", ["her2-", "erbb2 negative", "her2 negative", "her2/neu negative"]),
    ("C68750", "Estrogen Receptor Positive", ["er+", "er positive", "estrogen receptor positive"]),
    ("C68751", "Estrogen Receptor Negative", ["er-", "er negative", "estrogen receptor negative"]),
    ("C68752", "Progesterone Receptor Positive", ["pr+", "pr positive", "progesterone receptor positive"]),
    ("C68753", "Progesterone Receptor Negative", ["pr-", "pr negative", "progesterone receptor negative"]),
    ("C128839", "PD-L1 Positive", ["pd-l1+", "pd-l1 positive", "pdl1 positive", "pd l1 positive", "pdl1+"]),
    ("C126808", "EGFR Mutation Positive", ["egfr+", "egfr mutant", "egfr mutation positive", "egfr mutated"]),
    ("C126813", "ALK Rearrangement Positive", ["alk+", "alk positive", "alk rearrangement", "alk rearranged"]),
    ("C126817", "BRAF V600E Mutation Positive", ["braf v600e", "braf mutant", "braf mutation positive"]),
    (
        "C126815",
        "KRAS Mutation Positive",
        ["kras", "kras mutant", "kras mutation positive", "kras g12c", "kras g12c mutation"],
    ),
    ("C126814", "ROS1 Rearrangement Positive", ["ros1+", "ros1 positive", "ros1 rearrangement", "ros1 rearranged"]),
    ("C142080", "NTRK Fusion Positive", ["ntrk+", "ntrk fusion", "ntrk positive", "ntrk fusion positive"]),
    ("C121553", "Microsatellite Instability-High", ["msi-h", "msi high", "microsatellite instability high", "msih"]),
    ("C177609", "Tumor Mutational Burden-High", ["tmb-h", "tmb high", "tumor mutational burden high", "tmbh"]),
    ("C126818", "BRCA1 Mutation", ["brca1 mutant", "brca1 mutation", "brca1 pathogenic variant"]),
    ("C126819", "BRCA2 Mutation", ["brca2 mutant", "brca2 mutation", "brca2 pathogenic variant"]),
    ("C129789", "PIK3CA Mutation", ["pik3ca mutant", "pik3ca mutation"]),
    ("C129686", "FGFR Alteration", ["fgfr+", "fgfr alteration", "fgfr mutation"]),
    ("C129790", "MET Amplification", ["met amplified", "met amplification"]),
]

# NCI Thesaurus drug codes
NCI_DRUGS = [
    ("C1647", "Trastuzumab", ["herceptin"]),
    ("C1857", "Pertuzumab", ["perjeta"]),
    ("C2878", "Bevacizumab", ["avastin"]),
    ("C1702", "Rituximab", ["rituxan", "mabthera"]),
    ("C1873", "Pembrolizumab", ["keytruda"]),
    ("C1872", "Nivolumab", ["opdivo"]),
    ("C1871", "Atezolizumab", ["tecentriq"]),
    ("C1874", "Durvalumab", ["imfinzi"]),
    ("C1875", "Ipilimumab", ["yervoy"]),
    ("C1671", "Paclitaxel", ["taxol"]),
    ("C1526", "Docetaxel", ["taxotere"]),
    ("C408", "Cisplatin", ["platinol"]),
    ("C1282", "Carboplatin", ["paraplatin"]),
    ("C1512", "Gemcitabine", ["gemzar"]),
    ("C490", "Doxorubicin", ["adriamycin"]),
    ("C62040", "T-DM1", ["ado-trastuzumab emtansine", "ado trastuzumab emtansine", "kadcyla"]),
    (
        "C157437",
        "Trastuzumab Deruxtecan",
        ["enhertu", "t-dxd", "ds-8201", "fam trastuzumab deruxtecan", "fam trastuzumab deruxtecan nxki"],
    ),
    ("C1878", "Olaparib", ["lynparza"]),
    ("C1879", "Rucaparib", ["rubraca"]),
    ("C1880", "Niraparib", ["zejula"]),
    ("C1884", "Palbociclib", ["ibrance"]),
    ("C1885", "Ribociclib", ["kisqali"]),
    ("C1886", "Abemaciclib", ["verzenio"]),
    ("C1167", "Tamoxifen", ["nolvadex"]),
    ("C1808", "Letrozole", ["femara"]),
    ("C62556", "Osimertinib", ["tagrisso"]),
    ("C62557", "Crizotinib", ["xalkori"]),
    ("C62558", "Alectinib", ["alecensa"]),
    ("C62559", "Lorlatinib", ["lorbrena"]),
    ("C62560", "Sotorasib", ["lumakras"]),
    ("C62561", "Adagrasib", ["krazati"]),
    ("C62562", "Dabrafenib", ["tafinlar"]),
    ("C62563", "Trametinib", ["mekinist"]),
    ("C62564", "Vemurafenib", ["zelboraf"]),
    ("C62565", "Encorafenib", ["braftovi"]),
    (
        "C128057",
        "anti-PD-L1 monoclonal antibody",
        [
            "pd-l1 therapy",
            "pd l1 therapy",
            "pd-l1 inhibitor therapy",
            "programmed death-ligand 1 therapy",
            "programmed death ligand 1 therapy",
        ],
    ),
    ("C1794", "Capecitabine", ["xeloda"]),
    ("C1900", "Irinotecan", ["camptosar"]),
    ("C510", "Fluorouracil", ["5-fu", "5fu", "5 fluorouracil"]),
]

# LOINC lab test codes
LOINC_LABS = [
    ("26464-8", "Leukocytes [#/volume] in Blood", ["wbc", "white blood cell count", "leukocyte count"]),
    ("751-8", "Neutrophils [#/volume] in Blood", ["anc", "absolute neutrophil count", "absolute neutrophils"]),
    ("26515-7", "Platelets [#/volume] in Blood", ["platelet count", "thrombocyte count"]),
    ("718-7", "Hemoglobin [Mass/volume] in Blood", ["hemoglobin", "hgb", "hb"]),
    (
        "1742-6",
        "Alanine aminotransferase [Enzymatic activity/volume] in Serum",
        ["alt", "sgpt", "alanine aminotransferase"],
    ),
    (
        "1920-8",
        "Aspartate aminotransferase [Enzymatic activity/volume] in Serum",
        ["ast", "sgot", "aspartate aminotransferase"],
    ),
    ("1975-2", "Bilirubin.total [Mass/volume] in Serum", ["total bilirubin", "bilirubin", "serum bilirubin"]),
    ("2160-0", "Creatinine [Mass/volume] in Serum", ["creatinine", "serum creatinine", "serum creatinine level"]),
    ("33914-3", "Glomerular filtration rate/1.73 sq M.predicted", ["gfr", "egfr", "glomerular filtration rate"]),
    ("6690-2", "Creatinine Clearance", ["crcl", "creatinine clearance"]),
    ("6301-6", "INR in Platelet poor plasma", ["inr", "international normalized ratio"]),
    ("58410-2", "CBC panel", ["cbc", "complete blood count"]),
]

# Performance scales (NCI codes)
NCI_SCALES = [
    ("C105721", "ECOG Performance Status", ["ecog", "ecog ps", "ecog performance status"]),
    ("C28007", "Karnofsky Performance Status", ["kps", "karnofsky", "karnofsky performance status"]),
]

# SNOMED CT procedure/specimen codes
SNOMED_PROCEDURES = [
    (
        "17636008",
        "Specimen collection",
        ["archival tumor tissue", "archival tumor tissue sample", "tumor tissue sample", "provided tissue"],
    ),
    ("86273004", "Biopsy", ["newly obtained biopsy", "tumor biopsy"]),
    ("387713003", "Surgical procedure", ["major surgery", "surgical complications"]),
]


def seed():
    db = SessionLocal()
    try:
        inserted = 0
        updated = 0

        for system, rows in (
            ("mesh", MESH_DISEASES),
            ("nci_thesaurus", NCI_BIOMARKERS + NCI_DRUGS + NCI_SCALES),
            ("snomed_ct", SNOMED_PROCEDURES),
            ("loinc", LOINC_LABS),
        ):
            for code, display, synonyms in rows:
                created, changed = _upsert_lookup(
                    db=db,
                    system=system,
                    code=code,
                    display=display,
                    synonyms=synonyms,
                )
                inserted += int(created)
                updated += int(changed)

        db.commit()
        print(f"Seeded {inserted} coding lookups.")
        print(f"Updated {updated} coding lookups.")
        total = db.query(CodingLookup).count()
        print(f"Total coding lookups in database: {total}")
    finally:
        db.close()


def _upsert_lookup(db, system: str, code: str, display: str, synonyms: list[str]) -> tuple[bool, bool]:
    existing = db.query(CodingLookup).filter_by(system=system, code=code).first()
    normalized_synonyms = _merge_synonyms([], synonyms)
    if existing is None:
        db.add(CodingLookup(system=system, code=code, display=display, synonyms=normalized_synonyms))
        return True, False

    changed = False
    if existing.display != display:
        existing.display = display
        changed = True

    merged_synonyms = _merge_synonyms(existing.synonyms or [], synonyms)
    if merged_synonyms != (existing.synonyms or []):
        existing.synonyms = merged_synonyms
        changed = True

    return False, changed


def _merge_synonyms(current: list[str], desired: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*current, *desired]:
        normalized = value.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        merged.append(normalized)
        seen.add(key)
    return merged


if __name__ == "__main__":
    seed()
