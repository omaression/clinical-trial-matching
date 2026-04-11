"""FHIR R4 Pydantic models for ResearchStudy resource validation.

These models validate the structure of FHIR resources before persistence.
They are intentionally lightweight — the full FHIR spec is complex, and
we only model the subset used by the mapper.
"""

from pydantic import BaseModel, Field


class Identifier(BaseModel):
    system: str | None = None
    value: str


class Coding(BaseModel):
    system: str
    code: str
    display: str | None = None


class CodeableConcept(BaseModel):
    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Extension(BaseModel):
    url: str
    valueString: str | None = None
    valueDecimal: float | None = None
    valueCoding: Coding | None = None
    extension: list["Extension"] = Field(default_factory=list)


class ResearchStudy(BaseModel):
    """FHIR R4 ResearchStudy resource (subset)."""
    resourceType: str = "ResearchStudy"
    identifier: list[Identifier] = Field(default_factory=list)
    title: str | None = None
    status: str = "active"
    phase: CodeableConcept | None = None
    condition: list[CodeableConcept] = Field(default_factory=list)
    extension: list[Extension] = Field(default_factory=list)
    enrollment: list[dict] | None = None
