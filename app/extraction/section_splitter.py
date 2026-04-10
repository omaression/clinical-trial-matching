import re

from app.extraction.types import CriterionText

# Patterns for section headers
_INCLUSION_HEADER = re.compile(r"(?i)^\s*(inclusion\s+criteria|eligibility\s+criteria|inclusion)\s*:?\s*$")
_EXCLUSION_HEADER = re.compile(r"(?i)^\s*(exclusion\s+criteria|exclusion)\s*:?\s*$")
_NUMBERED_ITEM = re.compile(r"^\s*(?:\d+[\.\)]\s*|-\s*|•\s*)")

# Polarity signals for fallback classification
_EXCLUSION_SIGNALS = [
    re.compile(r"\bmust\s+not\b", re.I),
    re.compile(r"\bshould\s+not\b", re.I),
    re.compile(r"\bcannot\b", re.I),
    re.compile(r"\bno\s+(?:prior|history|evidence|active|known)\b", re.I),
    re.compile(r"\bno\s+(?:prior\s+)?(?:systemic|concurrent)\b", re.I),
    re.compile(r"\babsence\s+of\b", re.I),
    re.compile(r"\bexcluded?\s+if\b", re.I),
    re.compile(r"\bineligible\s+if\b", re.I),
    re.compile(r"\bhave\s+not\s+received\b", re.I),
    re.compile(r"\bnot\s+have\s+(?:received|active|known)\b", re.I),
    re.compile(r"\bwithout\s+(?:prior|active|known|evidence)\b", re.I),
]


class SectionSplitter:
    """Stage 1: Split raw eligibility text into individual criteria."""

    def split(self, text: str) -> list[CriterionText]:
        if not text or not text.strip():
            return []

        lines = text.strip().split("\n")
        has_headers = any(_INCLUSION_HEADER.match(l) or _EXCLUSION_HEADER.match(l) for l in lines)

        if has_headers:
            return self._split_with_headers(lines)
        return self._split_by_polarity(lines)

    def _split_with_headers(self, lines: list[str]) -> list[CriterionText]:
        results = []
        current_type = "inclusion"

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _INCLUSION_HEADER.match(stripped):
                current_type = "inclusion"
                continue
            if _EXCLUSION_HEADER.match(stripped):
                current_type = "exclusion"
                continue

            criterion_text = _NUMBERED_ITEM.sub("", stripped).strip()
            if not criterion_text:
                continue

            # Check for polarity override
            detected_type = self._detect_polarity(criterion_text)
            if detected_type == "exclusion" and current_type == "inclusion":
                results.append(CriterionText(
                    text=criterion_text,
                    type="exclusion",
                    review_required=True,
                    review_reason="polarity_override",
                ))
            else:
                results.append(CriterionText(text=criterion_text, type=current_type))

        return results

    def _split_by_polarity(self, lines: list[str]) -> list[CriterionText]:
        results = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            criterion_text = _NUMBERED_ITEM.sub("", stripped).strip()
            if not criterion_text:
                continue
            detected = self._detect_polarity(criterion_text)
            results.append(CriterionText(text=criterion_text, type=detected))
        return results

    def _detect_polarity(self, text: str) -> str:
        for pattern in _EXCLUSION_SIGNALS:
            if pattern.search(text):
                return "exclusion"
        return "inclusion"
