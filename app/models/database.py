import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship

from app.time_utils import utc_now


class Base(DeclarativeBase):
    pass


class Trial(Base):
    __tablename__ = "trials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nct_id = Column(String, unique=True, nullable=False, index=True)
    raw_json = Column(JSONB, nullable=False)
    content_hash = Column(String, nullable=False, index=True)
    brief_title = Column(String, nullable=False)
    official_title = Column(String)
    status = Column(String, nullable=False, index=True)
    phase = Column(String, index=True)
    conditions = Column(ARRAY(String))
    interventions = Column(JSONB)
    eligibility_text = Column(Text)
    # Structured eligibility from ClinicalTrials.gov
    eligible_min_age = Column(String)
    eligible_max_age = Column(String)
    eligible_sex = Column(String)
    accepts_healthy = Column(Boolean)
    structured_eligibility = Column(JSONB)
    sponsor = Column(String)
    start_date = Column(DateTime(timezone=True))
    completion_date = Column(DateTime(timezone=True))
    last_updated = Column(DateTime(timezone=True))
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True))
    extraction_status = Column(String, nullable=False, default="pending")

    sites = relationship("TrialSite", back_populates="trial", cascade="all, delete-orphan")
    criteria = relationship("ExtractedCriterion", back_populates="trial", cascade="all, delete-orphan")
    pipeline_runs = relationship("PipelineRun", back_populates="trial", cascade="all, delete-orphan")
    fhir_studies = relationship("FHIRResearchStudy", back_populates="trial", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_trials_conditions", "conditions", postgresql_using="gin"),)


class TrialSite(Base):
    __tablename__ = "trial_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("trials.id", ondelete="CASCADE"), nullable=False, index=True)
    facility = Column(String)
    city = Column(String)
    state = Column(String)
    country = Column(String)
    zip = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    status = Column(String)

    trial = relationship("Trial", back_populates="sites")

    __table_args__ = (Index("ix_trial_sites_geo", "country", "state", "city"),)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("trials.id", ondelete="CASCADE"), nullable=False, index=True)
    pipeline_version = Column(String, nullable=False, index=True)
    input_hash = Column(String, nullable=False)
    input_snapshot = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default="running")
    started_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    criteria_extracted_count = Column(Integer)
    review_required_count = Column(Integer)
    diff_summary = Column(JSONB)

    trial = relationship("Trial", back_populates="pipeline_runs")
    criteria = relationship("ExtractedCriterion", back_populates="pipeline_run")
    fhir_study = relationship("FHIRResearchStudy", back_populates="pipeline_run", uselist=False)


class FHIRResearchStudy(Base):
    __tablename__ = "fhir_research_studies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("trials.id", ondelete="CASCADE"), nullable=False)
    resource = Column(JSONB, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True))

    trial = relationship("Trial", back_populates="fhir_studies")
    pipeline_run = relationship("PipelineRun", back_populates="fhir_study")


class ExtractedCriterion(Base):
    __tablename__ = "extracted_criteria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("trials.id", ondelete="CASCADE"), nullable=False, index=True)
    # Classification
    type = Column(String, nullable=False)  # inclusion / exclusion
    category = Column(String, nullable=False, index=True)
    parse_status = Column(String, nullable=False, default="parsed")  # parsed / partial / unparsed
    # Original text
    original_text = Column(Text, nullable=False)
    # Value extraction
    operator = Column(String)
    value_low = Column(Float)
    value_high = Column(Float)
    value_text = Column(String)
    unit = Column(String)
    raw_expression = Column(String)
    negated = Column(Boolean, nullable=False, default=False)
    # Temporal modifiers
    timeframe_operator = Column(String)
    timeframe_value = Column(Float)
    timeframe_unit = Column(String)
    # Logic grouping
    logic_group_id = Column(UUID(as_uuid=True))
    logic_operator = Column(String, nullable=False, default="AND")
    # Coding
    coded_concepts = Column(JSONB, default=list)
    # Confidence & provenance
    confidence = Column(Float, nullable=False, default=0.0)
    review_required = Column(Boolean, nullable=False, default=False)
    review_reason = Column(String)
    # Review outcomes
    review_status = Column(String)  # pending / accepted / corrected / rejected
    reviewed_by = Column(String)
    reviewed_at = Column(DateTime(timezone=True))
    review_notes = Column(Text)
    original_extracted = Column(JSONB)
    # Provenance
    pipeline_version = Column(String, nullable=False)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    trial = relationship("Trial", back_populates="criteria")
    pipeline_run = relationship("PipelineRun", back_populates="criteria")

    __table_args__ = (
        Index("ix_criteria_review", "review_required", postgresql_where="review_required = true"),
        Index("ix_criteria_coded", "coded_concepts", postgresql_using="gin"),
    )


class CodingLookup(Base):
    __tablename__ = "coding_lookups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    system = Column(String, nullable=False)
    code = Column(String, nullable=False)
    display = Column(String, nullable=False)
    synonyms = Column(ARRAY(String), default=list)
    parent_codes = Column(ARRAY(String), default=list)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("system", "code", name="uq_coding_system_code"),
        Index("ix_coding_synonyms", "synonyms", postgresql_using="gin"),
    )
