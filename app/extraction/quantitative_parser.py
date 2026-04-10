import re

from app.extraction.types import Entity, QuantitativeValue

# Operator mappings
_OP_MAP = {
    "≥": "gte", ">=": "gte", ">": "gte",
    "≤": "lte", "<=": "lte", "<": "lte",
    "=": "eq",
}
_WORD_OP_MAP = {
    "at least": "gte",
    "no more than": "lte",
    "less than": "lte",
    "greater than": "gte",
    "more than": "gte",
}

# Superscript digit mapping
_SUPERSCRIPT_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
}

# Regex patterns
_SCI_NOTATION = re.compile(
    r"(?P<op>[≥≤><]=?)\s*(?P<val>[\d.]+)\s*[x×]\s*10(?P<exp_raw>[⁰¹²³⁴⁵⁶⁷⁸⁹]+)\s*(?P<unit>.*)"
)
_RANGE = re.compile(
    r"(?P<low>[\d.]+)\s*[-–]\s*(?P<high>[\d.]+)\s*(?P<unit>.*)"
)
_WORD_COMP = re.compile(
    r"(?P<op>at least|no more than|less than|greater than|more than)\s+(?P<val>[\d.]+)\s*(?P<unit>.*)",
    re.I,
)
_COMPARISON = re.compile(
    r"(?P<op>[≥≤><]=?)\s*(?P<val>[\d.]+)\s*(?P<unit>.*)"
)


def _parse_superscript(s: str) -> int:
    digits = "".join(_SUPERSCRIPT_MAP.get(c, "") for c in s)
    return int(digits) if digits else 9


class QuantitativeParser:
    """Stage 3 sub-component: decompose numeric expressions."""

    def parse(self, text: str, entities: list[Entity]) -> QuantitativeValue | None:
        text = text.strip()

        # Try scientific notation first (most specific)
        m = _SCI_NOTATION.match(text)
        if m:
            exp = _parse_superscript(m.group("exp_raw") or "⁹")
            val = float(m.group("val")) * (10 ** exp)
            unit = m.group("unit").strip()
            if unit and not unit.startswith("/"):
                unit = "/" + unit
            return QuantitativeValue(
                operator=_OP_MAP.get(m.group("op"), "gte"),
                value_low=val,
                unit=unit or None,
                raw_expression=text,
            )

        # Try range
        m = _RANGE.match(text)
        if m:
            return QuantitativeValue(
                operator="range",
                value_low=float(m.group("low")),
                value_high=float(m.group("high")),
                unit=m.group("unit").strip() or None,
                raw_expression=text,
            )

        # Try word operators
        m = _WORD_COMP.match(text)
        if m:
            return QuantitativeValue(
                operator=_WORD_OP_MAP[m.group("op").lower()],
                value_low=float(m.group("val")),
                unit=m.group("unit").strip() or None,
                raw_expression=text,
            )

        # Try simple comparison
        m = _COMPARISON.match(text)
        if m:
            unit = m.group("unit").strip()
            # Handle "× ULN" style relative units
            if unit and ("ULN" in unit or "LLN" in unit):
                if not unit.startswith("×"):
                    unit = "× " + unit
            return QuantitativeValue(
                operator=_OP_MAP.get(m.group("op"), "gte"),
                value_low=float(m.group("val")),
                unit=unit or None,
                raw_expression=text,
            )

        return None
