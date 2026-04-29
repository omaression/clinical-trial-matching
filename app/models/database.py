import uuid

from sqlalchemy import (
    Boolean,
    Column,
    Date,
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
    match_results = relationship("MatchResult", back_populates="trial", cascade="all, delete-orphan")

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
    source_sentence = Column(Text)
    source_clause_text = Column(Text)
    primary_semantic_category = Column(String)
    secondary_semantic_tags = Column(JSONB, default=list)
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
    specimen_type = Column(String)
    testing_modality = Column(String)
    disease_subtype = Column(String)
    histology_text = Column(String)
    assay_context = Column(JSONB)
    exception_logic = Column(JSONB)
    exception_entities = Column(JSONB, default=list)
    allowance_text = Column(Text)
    # Logic grouping
    logic_group_id = Column(UUID(as_uuid=True))
    logic_operator = Column(String, nullable=False, default="AND")
    # Coding
    coded_concepts = Column(JSONB, default=list)
    # Confidence & provenance
    confidence = Column(Float, nullable=False, default=0.0)
    confidence_factors = Column(JSONB)
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


class Patient(Base):
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id = Column(String, unique=True)
    sex = Column(String)
    birth_date = Column(Date)
    ecog_status = Column(Integer)
    is_healthy_volunteer = Column(Boolean)
    can_consent = Column(Boolean)
    protocol_compliant = Column(Boolean)
    claustrophobic = Column(Boolean)
    motion_intolerant = Column(Boolean)
    pregnant = Column(Boolean)
    mr_device_present = Column(Boolean)
    country = Column(String)
    state = Column(String)
    city = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True))

    conditions = relationship("PatientCondition", back_populates="patient", cascade="all, delete-orphan")
    biomarkers = relationship("PatientBiomarker", back_populates="patient", cascade="all, delete-orphan")
    labs = relationship("PatientLab", back_populates="patient", cascade="all, delete-orphan")
    therapies = relationship("PatientTherapy", back_populates="patient", cascade="all, delete-orphan")
    medications = relationship("PatientMedication", back_populates="patient", cascade="all, delete-orphan")
    match_runs = relationship("MatchRun", back_populates="patient", cascade="all, delete-orphan")
    match_results = relationship("MatchResult", back_populates="patient", cascade="all, delete-orphan")


class PatientCondition(Base):
    __tablename__ = "patient_conditions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String, nullable=False)
    coded_concepts = Column(JSONB, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    patient = relationship("Patient", back_populates="conditions")


class PatientBiomarker(Base):
    __tablename__ = "patient_biomarkers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String, nullable=False)
    coded_concepts = Column(JSONB, default=list)
    value_text = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    patient = relationship("Patient", back_populates="biomarkers")


class PatientLab(Base):
    __tablename__ = "patient_labs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String, nullable=False)
    coded_concepts = Column(JSONB, default=list)
    value_numeric = Column(Float)
    value_text = Column(String)
    unit = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    patient = relationship("Patient", back_populates="labs")


class PatientTherapy(Base):
    __tablename__ = "patient_therapies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String, nullable=False)
    coded_concepts = Column(JSONB, default=list)
    line_of_therapy = Column(Integer)
    completed = Column(Boolean)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    patient = relationship("Patient", back_populates="therapies")


class PatientMedication(Base):
    __tablename__ = "patient_medications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    description = Column(String, nullable=False)
    coded_concepts = Column(JSONB, default=list)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    patient = relationship("Patient", back_populates="medications")


class MatchRun(Base):
    __tablename__ = "match_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False, default="completed")
    total_trials_evaluated = Column(Integer, nullable=False, default=0)
    eligible_trials = Column(Integer, nullable=False, default=0)
    possible_trials = Column(Integer, nullable=False, default=0)
    ineligible_trials = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    patient = relationship("Patient", back_populates="match_runs")
    results = relationship("MatchResult", back_populates="match_run", cascade="all, delete-orphan")


class MatchResult(Base):
    __tablename__ = "match_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("match_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("trials.id", ondelete="CASCADE"), nullable=False, index=True)
    overall_status = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False, default=0.0)
    favorable_count = Column(Integer, nullable=False, default=0)
    unfavorable_count = Column(Integer, nullable=False, default=0)
    unknown_count = Column(Integer, nullable=False, default=0)
    requires_review_count = Column(Integer, nullable=False, default=0)
    summary_explanation = Column(Text)
    gap_report_payload = Column(JSONB)
    state = Column(String, nullable=False)
    state_reason = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    match_run = relationship("MatchRun", back_populates="results")
    patient = relationship("Patient", back_populates="match_results")
    trial = relationship("Trial", back_populates="match_results")
    criteria = relationship("MatchResultCriterion", back_populates="match_result", cascade="all, delete-orphan")
    review_items = relationship("MatchReviewItem", back_populates="match_result", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("match_run_id", "trial_id", name="uq_match_run_trial"),
    )


class MatchReviewItem(Base):
    __tablename__ = "match_review_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_result_id = Column(
        UUID(as_uuid=True), ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_run_id = Column(
        UUID(as_uuid=True), ForeignKey("match_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id = Column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trial_id = Column(
        UUID(as_uuid=True), ForeignKey("trials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_key = Column(String, nullable=False)
    bucket = Column(String, nullable=False, index=True)
    reason_code = Column(String, nullable=False, index=True)
    category = Column(String, nullable=False)
    criterion_text = Column(Text, nullable=False)
    outcome = Column(String)
    state = Column(String, nullable=False)
    state_reason = Column(String)
    source_snippet = Column(Text)
    evidence_payload = Column(JSONB)
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    match_result = relationship("MatchResult", back_populates="review_items")

    __table_args__ = (
        UniqueConstraint("match_result_id", "item_key", name="uq_match_review_item_result_key"),
        Index("ix_match_review_items_queue", "bucket", "reason_code", "created_at"),
    )


class MatchResultCriterion(Base):
    __tablename__ = "match_result_criteria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_result_id = Column(
        UUID(as_uuid=True), ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion_id = Column(UUID(as_uuid=True), ForeignKey("extracted_criteria.id"), nullable=True, index=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True, index=True)
    source_type = Column(String, nullable=False)
    source_label = Column(String, nullable=False)
    criterion_type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    criterion_text = Column(Text, nullable=False)
    outcome = Column(String, nullable=False)
    state = Column(String, nullable=False)
    state_reason = Column(String)
    explanation_text = Column(Text)
    explanation_type = Column(String)
    evidence_payload = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    match_result = relationship("MatchResult", back_populates="criteria")
    criterion = relationship("ExtractedCriterion")
    pipeline_run = relationship("PipelineRun")
