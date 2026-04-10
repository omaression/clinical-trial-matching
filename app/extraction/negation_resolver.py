import re
import uuid
from dataclasses import dataclass, field

from app.extraction.types import Entity, TemporalModifier

_NEGATION_TRIGGERS = re.compile(
    r"\b(no|not|without|never|absence of|must not|should not|cannot|have not|did not)\b", re.I
)
_EXCEPTION_SPLIT = re.compile(r"\b(unless|except|provided that|other than)\b", re.I)

_TEMPORAL_PATTERNS = [
    (re.compile(r"within\s+([\d.]+)\s+(days?|weeks?|months?|years?)", re.I), "within"),
    (re.compile(r"at\s+least\s+([\d.]+)\s+(days?|weeks?|months?|years?)", re.I), "at_least"),
    (re.compile(r"no\s+more\s+than\s+([\d.]+)\s+(days?|weeks?|months?|years?)", re.I), "no_more"),
    (re.compile(r"(?:>|more than)\s*([\d.]+)\s+(days?|weeks?|months?|years?)", re.I), "at_least"),
    (re.compile(r"prior\s+to\s+([\d.]+)\s+(days?|weeks?|months?|years?)", re.I), "prior_to"),
    (re.compile(r"since\s+([\d.]+)\s+(days?|weeks?|months?|years?)", re.I), "since"),
]

_OR_PATTERN = re.compile(r"\b(or|and/or)\b", re.I)


def _normalize_unit(unit: str) -> str:
    """Normalize temporal unit to consistently pluralized form."""
    singular = unit.rstrip("s").lower()
    return singular + "s"


@dataclass
class NegationResult:
    negated: bool = False
    negated_entities: list[str] = field(default_factory=list)
    has_exception: bool = False
    exception_text: str | None = None


@dataclass
class LogicResult:
    operator: str = "AND"
    group_id: str | None = None


class NegationResolver:
    """Stage 3 sub-component: distributed negation across coordinate structures."""

    def resolve(self, text: str, entities: list[Entity]) -> NegationResult:
        # Check for exception clauses first
        exception_match = _EXCEPTION_SPLIT.search(text)
        main_text = text[:exception_match.start()] if exception_match else text
        exception_text = text[exception_match.end():].strip() if exception_match else None

        # Check for negation trigger in main text
        neg_match = _NEGATION_TRIGGERS.search(main_text)
        if not neg_match:
            return NegationResult(negated=False)

        # All entities after the negation trigger are negated
        neg_pos = neg_match.start()
        negated_entities = []
        for e in entities:
            if e.start >= neg_pos:
                negated_entities.append(e.text)
        if not negated_entities:
            negated_entities = [e.text for e in entities]

        return NegationResult(
            negated=True,
            negated_entities=negated_entities,
            has_exception=exception_text is not None,
            exception_text=exception_text,
        )


class TemporalParser:
    """Stage 3 sub-component: extract timeframes."""

    def parse(self, text: str) -> TemporalModifier | None:
        for pattern, op in _TEMPORAL_PATTERNS:
            m = pattern.search(text)
            if m:
                unit = _normalize_unit(m.group(2))
                return TemporalModifier(
                    operator=op,
                    value=float(m.group(1)),
                    unit=unit,
                )
        return None


class LogicGrouper:
    """Stage 3 sub-component: detect AND/OR relationships."""

    def detect(self, text: str) -> LogicResult:
        if _OR_PATTERN.search(text):
            return LogicResult(operator="OR", group_id=str(uuid.uuid4()))
        return LogicResult(operator="AND")
