"""FHIR R4 Pydantic models for ResearchStudy resource validation.

These models validate the structure of FHIR resources before persistence.
They are intentionally lightweight — the full FHIR spec is complex, and
we only model the subset used by the mapper.
"""

from pydantic import BaseModel, ConfigDict, Field


class FHIRModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class Identifier(FHIRModel):
    system: str | None = None
    value: str


class Coding(FHIRModel):
    system: str
    code: str
    display: str | None = None


class CodeableConcept(FHIRModel):
    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Reference(FHIRModel):
    reference: str
    display: str | None = None


class Annotation(FHIRModel):
    text: str


class Extension(FHIRModel):
    url: str
    value_string: str | None = Field(default=None, alias="valueString")
    value_decimal: float | None = Field(default=None, alias="valueDecimal")
    value_coding: Coding | None = Field(default=None, alias="valueCoding")
    extension: list["Extension"] = Field(default_factory=list)


class ResearchStudy(FHIRModel):
    """FHIR R4 ResearchStudy resource (subset)."""

    resource_type: str = Field(default="ResearchStudy", alias="resourceType")
    identifier: list[Identifier] = Field(default_factory=list)
    title: str | None = None
    status: str = "active"
    phase: CodeableConcept | None = None
    condition: list[CodeableConcept] = Field(default_factory=list)
    extension: list[Extension] = Field(default_factory=list)
    enrollment: list[dict] | None = None


class MedicationStatement(FHIRModel):
    """FHIR R4 MedicationStatement resource (subset)."""

    resource_type: str = Field(default="MedicationStatement", alias="resourceType")
    status: str
    medication_codeable_concept: CodeableConcept = Field(alias="medicationCodeableConcept")
    subject: Reference
    derived_from: list[Reference] = Field(default_factory=list, alias="derivedFrom")
    note: list[Annotation] = Field(default_factory=list)
