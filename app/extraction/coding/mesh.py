"""MeSH term lookup utilities.

Maps disease entities to MeSH (Medical Subject Headings) codes via the
coding_lookups table. Used by EntityCoder for DISEASE-label entities.

The coding_lookups table is populated by the seed script
(app.scripts.seed) with common oncology MeSH codes. For production use,
this can be extended to query the NLM UMLS API for broader coverage.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import CodingLookup


def lookup_mesh(db: Session, term: str) -> CodingLookup | None:
    """Find a MeSH coding lookup by exact display or synonym match."""
    # Exact match on display
    result = db.query(CodingLookup).filter(
        CodingLookup.system == "mesh",
        func.lower(CodingLookup.display) == term.lower(),
    ).first()
    if result:
        return result

    # Synonym match
    return db.query(CodingLookup).filter(
        CodingLookup.system == "mesh",
        CodingLookup.synonyms.any(func.lower(term)),
    ).first()
