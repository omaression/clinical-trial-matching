import re

from app.extraction.types import CriterionText

# Patterns for section headers
_INCLUSION_HEADER = re.compile(r"(?i)^\s*(inclusion\s+criteria|eligibility\s+criteria|inclusion)\s*:?\s*$")
_EXCLUSION_HEADER = re.compile(r"(?i)^\s*(exclusion\s+criteria|exclusion)\s*:?\s*$")
_NUMBERED_ITEM = re.compile(r"^\s*(?:\d+[\.\)]\s*|-\s*|•\s*)")
_SECTION_INTRO = re.compile(
    r"(?i)^\s*the\s+main\s+(?:inclusion|exclusion)\s+criteria\s+include(?:\s+but\s+are\s+not\s+limited\s+to)?"
    r"\s+the\s+following\s*:?\s*$"
)

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
        has_headers = any(_INCLUSION_HEADER.match(line) or _EXCLUSION_HEADER.match(line) for line in lines)

        if has_headers:
            return self._split_with_headers(lines)
        return self._split_by_polarity(lines)

    def _split_with_headers(self, lines: list[str]) -> list[CriterionText]:
        results = []
        current_type = "inclusion"
        current_parts: list[str] = []
        current_started_by_marker = False

        def flush_current() -> None:
            nonlocal current_parts, current_started_by_marker, results, current_type
            if not current_parts:
                return
            criterion_text = " ".join(current_parts).strip()
            current_parts = []
            current_started_by_marker = False
            if not criterion_text:
                return
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

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _INCLUSION_HEADER.match(stripped):
                flush_current()
                current_type = "inclusion"
                continue
            if _EXCLUSION_HEADER.match(stripped):
                flush_current()
                current_type = "exclusion"
                continue
            if _SECTION_INTRO.match(stripped):
                flush_current()
                continue

            if _NUMBERED_ITEM.match(line):
                flush_current()
                criterion_text = _NUMBERED_ITEM.sub("", stripped).strip()
                if criterion_text:
                    current_parts = [criterion_text]
                    current_started_by_marker = True
            else:
                if current_parts and (current_started_by_marker or line[:1].isspace()):
                    current_parts.append(stripped)
                else:
                    flush_current()
                    current_parts = [stripped]
                    current_started_by_marker = False

        flush_current()
        return results

    def _split_by_polarity(self, lines: list[str]) -> list[CriterionText]:
        results = []
        current_parts: list[str] = []
        current_started_by_marker = False

        def flush_current() -> None:
            nonlocal current_parts, current_started_by_marker, results
            if not current_parts:
                return
            criterion_text = " ".join(current_parts).strip()
            current_parts = []
            current_started_by_marker = False
            if not criterion_text:
                return
            detected = self._detect_polarity(criterion_text)
            results.append(CriterionText(text=criterion_text, type=detected))

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if _SECTION_INTRO.match(stripped):
                flush_current()
                continue
            if _NUMBERED_ITEM.match(line):
                flush_current()
                criterion_text = _NUMBERED_ITEM.sub("", stripped).strip()
                if criterion_text:
                    current_parts = [criterion_text]
                    current_started_by_marker = True
            else:
                if current_parts and (current_started_by_marker or line[:1].isspace()):
                    current_parts.append(stripped)
                else:
                    flush_current()
                    current_parts = [stripped]
                    current_started_by_marker = False
        flush_current()
        return results

    def _detect_polarity(self, text: str) -> str:
        for pattern in _EXCLUSION_SIGNALS:
            if pattern.search(text):
                return "exclusion"
        return "inclusion"
