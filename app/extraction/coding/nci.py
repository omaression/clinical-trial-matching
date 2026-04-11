"""NCI Thesaurus term lookup utilities.

Maps biomarker, drug, and performance scale entities to NCI Thesaurus
codes via the coding_lookups table. Used by EntityCoder for BIOMARKER,
DRUG, and PERF_SCALE label entities.

The coding_lookups table is populated by the seed script
(app.scripts.seed) with common oncology NCI codes.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import CodingLookup


def lookup_nci(db: Session, term: str) -> CodingLookup | None:
    """Find an NCI Thesaurus coding lookup by exact display or synonym match."""
    result = db.query(CodingLookup).filter(
        CodingLookup.system == "nci_thesaurus",
        func.lower(CodingLookup.display) == term.lower(),
    ).first()
    if result:
        return result

    return db.query(CodingLookup).filter(
        CodingLookup.system == "nci_thesaurus",
        CodingLookup.synonyms.any(func.lower(term)),
    ).first()
