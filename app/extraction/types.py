from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class CriterionText(BaseModel):
    """Output of Stage 1: Section Splitter."""
    text: str
    type: str  # "inclusion" | "exclusion"
    review_required: bool = False
    review_reason: str | None = None
    source_sentence: str | None = None


class Entity(BaseModel):
    """A recognized entity span from Stage 2 NER."""
    text: str
    label: str  # DISEASE, DRUG, BIOMARKER, LAB_TEST, MEASURE, PERF_SCALE, TIMEFRAME, THERAPY_LINE
    start: int
    end: int
    expanded_text: str | None = None  # From Stage 2.5 abbreviation resolver

    @property
    def display_text(self) -> str:
        return self.text

    @property
    def lookup_text(self) -> str:
        """Text used for coding lookup — expanded form if available."""
        return self.expanded_text or self.text


class QuantitativeValue(BaseModel):
    """Parsed numeric expression from Stage 3 QuantitativeParser."""
    operator: str  # eq, gte, lte, range, present, absent, contains
    value_low: float | None = None
    value_high: float | None = None
    value_text: str | None = None
    unit: str | None = None
    raw_expression: str | None = None


class TemporalModifier(BaseModel):
    """Parsed timeframe from Stage 3 TemporalParser."""
    operator: str  # within, at_least, no_more, prior_to, since
    value: float
    unit: str  # days, weeks, months, years


class CodedConcept(BaseModel):
    """A mapped coding system reference."""
    system: str  # mesh, nci_thesaurus, loinc
    code: str
    display: str
    match_type: str = "exact"  # exact, synonym, fuzzy


class ClassifiedCriterion(BaseModel):
    """Fully classified criterion — output of Stage 3, enriched by Stage 4."""
    original_text: str
    source_sentence: str | None = None
    type: str  # inclusion / exclusion
    category: str
    parse_status: str = "parsed"  # parsed / partial / unparsed
    # Value extraction
    operator: str | None = None
    value_low: float | None = None
    value_high: float | None = None
    value_text: str | None = None
    unit: str | None = None
    raw_expression: str | None = None
    negated: bool = False
    # Temporal
    timeframe_operator: str | None = None
    timeframe_value: float | None = None
    timeframe_unit: str | None = None
    # Logic grouping
    logic_group_id: str | None = None  # UUID as string
    logic_operator: str = "AND"
    # Coding (populated by Stage 4)
    coded_concepts: list[CodedConcept] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    # Confidence
    confidence: float = 0.0
    review_required: bool = False
    review_reason: str | None = None

    @classmethod
    def unparsed(cls, original_text: str, type: str) -> ClassifiedCriterion:
        return cls(
            original_text=original_text,
            type=type,
            category="other",
            parse_status="unparsed",
            confidence=0.0,
            review_required=True,
            review_reason="complex_criteria",
        )


class PipelineResult(BaseModel):
    """Complete output of the extraction pipeline for one trial."""
    criteria: list[ClassifiedCriterion]
    pipeline_version: str

    @property
    def criteria_count(self) -> int:
        return len(self.criteria)

    @property
    def review_required_count(self) -> int:
        return sum(1 for c in self.criteria if c.review_required)


class CriteriaClassifierProtocol(Protocol):
    """Pluggable strategy interface for Stage 3."""
    def classify(self, criterion_text: str, entities: list[Entity]) -> ClassifiedCriterion: ...
