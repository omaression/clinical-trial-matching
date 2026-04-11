import json
from pathlib import Path

from app.extraction.types import Entity


class AbbreviationResolver:
    """Stage 2.5: Expand oncology acronyms before coding lookup."""

    def __init__(self, dict_path: str = "data/dictionaries/onc_abbreviations.jsonl"):
        self._dict: dict[str, str] = {}
        self._load_dictionary(dict_path)

    def _load_dictionary(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            return
        with open(p) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                self._dict[entry["abbr"].lower()] = entry["expansion"]

    def resolve(
        self,
        entities: list[Entity],
        text: str,
        dynamic_abbreviations: dict[str, str] | None = None,
    ) -> list[Entity]:
        """Expand abbreviations on entities. Returns new list with expanded_text set."""
        result = []
        dynamic_abbreviations = dynamic_abbreviations or {}
        for entity in entities:
            expanded = dynamic_abbreviations.get(entity.text.lower()) or self._lookup(entity.text)
            result.append(entity.model_copy(update={"expanded_text": expanded}))
        return result

    def _lookup(self, text: str) -> str | None:
        if " " in text.strip():
            return None
        return self._dict.get(text.lower())
